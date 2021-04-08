from datetime import date, time, datetime, timedelta

import pandas as pd
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from etc.scripts import fill_calendar
from src.base.tests.factories import ShopFactory, UserFactory, GroupFactory, EmploymentFactory, NetworkFactory
from src.recognition.models import Tick
from src.timetable.models import WorkerDay
from src.timetable.tests.factories import WorkerDayFactory, WorkTypeFactory
from src.util.mixins.tests import TestsHelperMixin


class MultipleActiveEmploymentsSupportMixin(TestsHelperMixin):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop1 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP1',
            network=cls.network,
        )
        cls.shop2 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP2',
            network=cls.network,
        )
        cls.shop3 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP3',
            network=cls.network,
        )
        cls.user1 = UserFactory(email='dir@example.com', network=cls.network)
        cls.user2 = UserFactory(email='urs@example.com', network=cls.network)

        cls.group1 = GroupFactory(network=cls.network)

        cls.work_type3_other = WorkTypeFactory(
            shop=cls.shop3,
            work_type_name__name='Другое',
        )

        cls.work_type1_cachier = WorkTypeFactory(
            shop=cls.shop1,
            work_type_name__name='Продавец-кассир',
        )
        cls.work_type2_cachier = WorkTypeFactory(
            shop=cls.shop2,
            work_type_name__name='Продавец-кассир',
        )
        cls.work_type3_cachier = WorkTypeFactory(
            shop=cls.shop3,
            work_type_name__name='Продавец-кассир',
        )

        cls.work_type1_cleaner = WorkTypeFactory(
            shop=cls.shop1,
            work_type_name__name='Уборщик',
        )
        cls.work_type2_cleaner = WorkTypeFactory(
            shop=cls.shop2,
            work_type_name__name='Уборщик',
        )
        cls.work_type3_cleaner = WorkTypeFactory(
            shop=cls.shop3,
            work_type_name__name='Уборщик',
        )

        # первая цифра -- user_id, вторая цифра -- shop_id, третья -- порядковый номер
        cls.employment1_1_1 = EmploymentFactory(
            user=cls.user1, shop=cls.shop1, function_group=cls.group1, network=cls.network,
            work_types__work_type=cls.work_type1_cachier,
            tabel_code='employment1_1_1',
        )
        cls.employment1_1_2 = EmploymentFactory(
            user=cls.user1, shop=cls.shop1, function_group=cls.group1, network=cls.network, norm_work_hours=50,
            work_types__work_type=cls.work_type1_cleaner,
            tabel_code='employment1_1_2',
        )
        cls.employment2_2_1 = EmploymentFactory(
            user=cls.user2, shop=cls.shop2, function_group=cls.group1, network=cls.network,
            work_types__work_type=cls.work_type2_cachier,
            tabel_code='employment2_2_1',
        )
        cls.employment2_3_1 = EmploymentFactory(
            user=cls.user2, shop=cls.shop3, function_group=cls.group1, network=cls.network, norm_work_hours=50,
            work_types__work_type=cls.work_type3_cachier,
            tabel_code='employment2_3_1',
        )
        cls.dt = date.today()
        fill_calendar.fill_days('2021.01.01', '2021.12.31', cls.shop1.region_id)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, TRUST_TICK_REQUEST=True)
class TestURVTicks(MultipleActiveEmploymentsSupportMixin, APITestCase):
    """
    Проверка работы отметок когда у пользователя несколько активных трудоустройств одновременно
    """
    @classmethod
    def setUpTestData(cls):
        super(TestURVTicks, cls).setUpTestData()
        cls.add_group_perm(cls.group1, 'Tick', 'POST')

    def _make_tick_requests(self, user, shop):
        self.client.force_authenticate(user=user)
        resp_coming = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': shop.code}),
            content_type='application/json',
        )
        self.assertEqual(resp_coming.status_code, status.HTTP_200_OK)

        resp_leaving = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_LEAVING, 'shop_code': shop.code}),
            content_type='application/json',
        )
        self.assertEqual(resp_leaving.status_code, status.HTTP_200_OK)

        self.assertEqual(Tick.objects.count(), 2)

        fact_approved = WorkerDay.objects.filter(
            worker=user,
            dt=self.dt,
            is_fact=True,
            is_approved=True,
        ).first()
        self.assertIsNotNone(fact_approved)
        return fact_approved

    def test_get_employment_from_plan(self):
        """
        Получение трудоустройства из плана
        """
        self.client.force_authenticate(user=self.user1)
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            worker=self.user1,
            employment=self.employment1_1_2,
            shop=self.shop1,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        fact_approved = self._make_tick_requests(self.user1, self.shop1)
        self.assertEqual(fact_approved.employment_id, self.employment1_1_2.id)
        self.assertIsNotNone(fact_approved.dttm_work_start)
        self.assertIsNotNone(fact_approved.dttm_work_end)

    def test_get_employment_for_user2_by_shop2(self):
        """
        Получение трудоустройства с приоритетом по подразделению в случае если нету плана (shop2)
        """
        self.client.force_authenticate(user=self.user2)
        fact_approved = self._make_tick_requests(self.user2, self.shop2)
        self.assertEqual(fact_approved.employment_id, self.employment2_2_1.id)

    def test_get_employment_for_user2_by_shop3(self):
        """
        Получение трудоустройства с приоритетом по подразделению в случае если нету плана (shop3)
        """
        self.client.force_authenticate(user=self.user2)
        fact_approved = self._make_tick_requests(self.user2, self.shop3)
        self.assertEqual(fact_approved.employment_id, self.employment2_3_1.id)

    def test_get_employment_by_max_norm_work_hours_when_multiple_active_empls_in_the_same_shop(self):
        """
        Получение трудоустройства с наибольшей ставкой
        """
        self.client.force_authenticate(user=self.user1)
        fact_approved = self._make_tick_requests(self.user1, self.shop1)
        self.assertEqual(fact_approved.employment_id, self.employment1_1_1.id)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, TRUST_TICK_REQUEST=True)
class TestConfirmVacancy(MultipleActiveEmploymentsSupportMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(TestConfirmVacancy, cls).setUpTestData()
        cls.dt_now = date.today()
        cls.add_group_perm(cls.group1, 'WorkerDay_confirm_vacancy', 'POST')
        WorkerDayFactory(
            dt=cls.dt_now,
            worker=cls.user1,
            is_fact=False,
            is_approved=True,
            type=WorkerDay.TYPE_HOLIDAY,
        )
        WorkerDayFactory(
            dt=cls.dt_now,
            worker=cls.user2,
            is_fact=False,
            is_approved=True,
            type=WorkerDay.TYPE_HOLIDAY,
        )

    def test_empl_received_by_cashier_work_type(self):
        vacancy = WorkerDayFactory(
            worker=None,
            employment=None,
            shop=self.shop1,
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_fact=False,
            is_approved=True,
            cashbox_details__work_type=self.work_type1_cachier,
        )
        self.client.force_authenticate(user=self.user1)
        resp = self.client.post(self.get_url('WorkerDay-confirm-vacancy', pk=vacancy.pk))
        self.assertEqual(resp.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employment_id, self.employment1_1_1.id)

    def test_empl_received_by_cleaner_work_type(self):
        vacancy = WorkerDayFactory(
            worker=None,
            employment=None,
            shop=self.shop1,
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_fact=False,
            is_approved=True,
            cashbox_details__work_type=self.work_type1_cleaner,
        )
        self.client.force_authenticate(user=self.user1)
        resp = self.client.post(self.get_url('WorkerDay-confirm-vacancy', pk=vacancy.pk))
        self.assertEqual(resp.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employment_id, self.employment1_1_2.id)

    def test_empl_received_by_shop_if_no_equal_work_type(self):
        vacancy = WorkerDayFactory(
            worker=None,
            employment=None,
            shop=self.shop3,
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_fact=False,
            is_approved=True,
            cashbox_details__work_type=self.work_type3_other,
        )
        self.client.force_authenticate(user=self.user2)
        resp = self.client.post(self.get_url('WorkerDay-confirm-vacancy', pk=vacancy.pk))
        self.assertEqual(resp.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employment_id, self.employment2_3_1.id)


class TestGetWorkersStatAndTabel(MultipleActiveEmploymentsSupportMixin, APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        super(TestGetWorkersStatAndTabel, cls).setUpTestData()
        cls.dt_now = date.today()
        cls.add_group_perm(cls.group1, 'WorkerDay', 'GET')
        cls.add_group_perm(cls.group1, 'WorkerDay_worker_stat', 'GET')

    def _create_wdays(self, dt_now):
        for dt in pd.date_range(dt_now, dt_now + timedelta(days=4)):
            WorkerDayFactory(
                dt=dt,
                worker=self.user1,
                employment=self.employment1_1_1,
                shop=self.shop1,
                type=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type1_cachier,
            )

        for dt in pd.date_range(dt_now + timedelta(days=5), dt_now + timedelta(days=9)):
            WorkerDayFactory(
                dt=dt,
                worker=self.user1,
                employment=self.employment1_1_1,
                shop=self.shop1,
                type=WorkerDay.TYPE_HOLIDAY,
                is_fact=False,
                is_approved=True,
            )

        for dt in pd.date_range(dt_now + timedelta(days=10), dt_now + timedelta(days=14)):
            WorkerDayFactory(
                dt=dt,
                worker=self.user1,
                employment=self.employment1_1_2,
                shop=self.shop1,
                type=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type1_cleaner,
            )

        for dt in pd.date_range(dt_now + timedelta(days=15), dt_now + timedelta(days=19)):
            WorkerDayFactory(
                dt=dt,
                worker=self.user1,
                shop=self.shop1,
                type=WorkerDay.TYPE_VACATION,
                is_fact=False,
                is_approved=True,
            )

        for dt in pd.date_range(dt_now + timedelta(days=20), dt_now + timedelta(days=24)):
            WorkerDayFactory(
                dt=dt,
                worker=self.user1,
                employment=self.employment1_1_2,
                shop=self.shop1,
                type=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type1_cleaner,
            )

    def test_get_tabel_data_by_tabel_code(self):
        """
        Проверка получения дней по табельному коду трудоустройства
        TODO: может ли быть такое, что у 1 пользователя отпуска по разным трудоустройствам будут в разные периоды? -- может!
        """
        self._create_wdays(self.dt_now)
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(
            self.get_url('WorkerDay-list'),
            data={
                'dt__gte': self.dt_now,
                'dt__lte': self.dt_now + timedelta(days=24),
                'fact_tabel': True,
                'employment__tabel_code__in': 'employment1_1_1',
            },
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 15)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_WORKDAY, resp_data))), 5)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_HOLIDAY, resp_data))), 5)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_VACATION, resp_data))), 5)

        resp = self.client.get(
            self.get_url('WorkerDay-list'),
            data={
                'dt__gte': self.dt_now,
                'dt__lte': self.dt_now + timedelta(days=24),
                'fact_tabel': True,
                'employment__tabel_code__in': 'employment1_1_2',
            },
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 20)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_WORKDAY, resp_data))), 10)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_HOLIDAY, resp_data))), 5)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_VACATION, resp_data))), 5)

    def test_get_worker_stat_by_tabel_code(self):
        """
        Проверка возможности получения статистики по табельному
        """
        self._create_wdays(date(2021, 3, 1))
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(
            self.get_url('WorkerDay-worker-stat'),
            data={
                'dt_from': date(2021, 3, 1),
                'dt_to': date(2021, 3, 31),
                'shop_id': self.shop1.id,
                'worker_id': self.user1.id,
            },
        )
        resp_data = resp.json()
        worker_data = resp_data.get(str(self.user1.id))
        empl_tabel_codes = worker_data.get('empl_tabel_codes')
        self.assertIn(self.employment1_1_1.tabel_code, empl_tabel_codes)
        self.assertDictEqual(
            empl_tabel_codes[self.employment1_1_1.tabel_code],
            {
                "fact": {
                    "approved": {
                        "work_days": {
                            "selected_shop": 5,
                            "other_shops": 0,
                            "total": 5
                        },
                        "work_hours": {
                            "selected_shop": 43.75,
                            "other_shops": 0.0,
                            "total": 43.75,
                            "until_acc_period_end": 43.75,
                            "acc_period": 43.75
                        },
                        "day_type": {
                            "W": 5
                        },
                        "norm_hours": {
                            "acc_period": 144.0,
                            "prev_months": 0.0,
                            "curr_month": 144.0,
                            "curr_month_end": 144.0
                        },
                        "overtime": {
                            "acc_period": -100.25,
                            "prev_months": 0.0,
                            "curr_month": -100.25,
                            "curr_month_end": -100.25
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 147.61290322580646
                            },
                            "selected_period": 147.61290322580646,
                            "curr_month": 147.61290322580646
                        }
                    },
                    "not_approved": {
                        "norm_hours": {
                            "acc_period": 144.0,
                            "prev_months": 0.0,
                            "curr_month": 144.0,
                            "curr_month_end": 144.0
                        },
                        "overtime": {
                            "acc_period": -144.0,
                            "prev_months": 0.0,
                            "curr_month": -144.0,
                            "curr_month_end": -144.0
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 147.61290322580646
                            },
                            "selected_period": 147.61290322580646,
                            "curr_month": 147.61290322580646
                        }
                    }
                },
                "plan": {
                    "approved": {
                        "work_days": {
                            "selected_shop": 0,
                            "other_shops": 0,
                            "total": 0
                        },
                        "work_hours": {
                            "selected_shop": 0.0,
                            "other_shops": 0.0,
                            "total": 0.0,
                            "until_acc_period_end": 0.0,
                            "prev_months": 0,
                            "acc_period": 0.0
                        },
                        "norm_hours": {
                            "acc_period": 144.0,
                            "prev_months": 0.0,
                            "curr_month": 144.0,
                            "curr_month_end": 144.0
                        },
                        "overtime": {
                            "acc_period": -144.0,
                            "prev_months": 0.0,
                            "curr_month": -144.0,
                            "curr_month_end": -144.0
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 147.61290322580646
                            },
                            "selected_period": 147.61290322580646,
                            "curr_month": 147.61290322580646
                        }
                    },
                    "not_approved": {
                        "norm_hours": {
                            "acc_period": 176.0,
                            "prev_months": 0.0,
                            "curr_month": 176.0,
                            "curr_month_end": 176.0
                        },
                        "overtime": {
                            "acc_period": -176.0,
                            "prev_months": 0.0,
                            "curr_month": -176.0,
                            "curr_month_end": -176.0
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 176.0
                            },
                            "selected_period": 176.0,
                            "curr_month": 176.0
                        }
                    }
                }
            }
        )
        self.assertIn(self.employment1_1_2.tabel_code, empl_tabel_codes)
        self.assertDictEqual(
            empl_tabel_codes[self.employment1_1_2.tabel_code],
            {
                "fact": {
                    "approved": {
                        "work_days": {
                            "selected_shop": 10,
                            "other_shops": 0,
                            "total": 10
                        },
                        "work_hours": {
                            "selected_shop": 87.5,
                            "other_shops": 0.0,
                            "total": 87.5,
                            "until_acc_period_end": 87.5,
                            "acc_period": 87.5
                        },
                        "day_type": {
                            "W": 10
                        },
                        "norm_hours": {
                            "acc_period": 72.0,
                            "prev_months": 0.0,
                            "curr_month": 72.0,
                            "curr_month_end": 72.0
                        },
                        "overtime": {
                            "acc_period": 15.5,
                            "prev_months": 0.0,
                            "curr_month": 15.5,
                            "curr_month_end": 15.5
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 73.80645161290323
                            },
                            "selected_period": 73.80645161290323,
                            "curr_month": 73.80645161290323
                        }
                    },
                    "not_approved": {
                        "norm_hours": {
                            "acc_period": 72.0,
                            "prev_months": 0.0,
                            "curr_month": 72.0,
                            "curr_month_end": 72.0
                        },
                        "overtime": {
                            "acc_period": -72.0,
                            "prev_months": 0.0,
                            "curr_month": -72.0,
                            "curr_month_end": -72.0
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 73.80645161290323
                            },
                            "selected_period": 73.80645161290323,
                            "curr_month": 73.80645161290323
                        }
                    }
                },
                "plan": {
                    "approved": {
                        "norm_hours": {
                            "acc_period": 72.0,
                            "prev_months": 0.0,
                            "curr_month": 72.0,
                            "curr_month_end": 72.0
                        },
                        "overtime": {
                            "acc_period": -72.0,
                            "prev_months": 0.0,
                            "curr_month": -72.0,
                            "curr_month_end": -72.0
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 73.80645161290323
                            },
                            "selected_period": 73.80645161290323,
                            "curr_month": 73.80645161290323
                        }
                    },
                    "not_approved": {
                        "norm_hours": {
                            "acc_period": 88.0,
                            "prev_months": 0.0,
                            "curr_month": 88.0,
                            "curr_month_end": 88.0
                        },
                        "overtime": {
                            "acc_period": -88.0,
                            "prev_months": 0.0,
                            "curr_month": -88.0,
                            "curr_month_end": -88.0
                        },
                        "sawh_hours": {
                            "by_months": {
                                "3": 88.0
                            },
                            "selected_period": 88.0,
                            "curr_month": 88.0
                        }
                    }
                }
            }
        )
