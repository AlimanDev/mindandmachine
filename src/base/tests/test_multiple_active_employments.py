from datetime import date, time, datetime, timedelta
from unittest import mock

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from etc.scripts import fill_calendar
from src.base.models import Employee
from src.base.tests.factories import (
    ShopFactory,
    UserFactory,
    GroupFactory,
    EmploymentFactory,
    NetworkFactory,
    EmployeeFactory,
)
from src.recognition.models import Tick
from src.timetable.models import WorkerDay, WorkerDayPermission, GroupWorkerDayPermission
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
        cls.user3 = UserFactory(email='urs@example.com', network=cls.network)

        cls.employee1_1 = EmployeeFactory(user=cls.user1, tabel_code='employee1_1')
        cls.employee1_2 = EmployeeFactory(user=cls.user1, tabel_code='employee1_2')
        cls.employee2_1 = EmployeeFactory(user=cls.user2, tabel_code='employee2_1')
        cls.employee2_2 = EmployeeFactory(user=cls.user2, tabel_code='employee2_2')
        cls.employee3 = EmployeeFactory(user=cls.user3, tabel_code='employee3')

        cls.group1 = GroupFactory(network=cls.network)
        cls.group2 = GroupFactory(network=cls.network)

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

        # первая цифра -- номер юзера, вторая -- номер сотрудника, третья цифра -- shop_id
        cls.employment1_1_1 = EmploymentFactory(
            employee=cls.employee1_1, shop=cls.shop1, function_group=cls.group1,
            work_types__work_type=cls.work_type1_cachier,
        )
        cls.employment1_2_1 = EmploymentFactory(
            employee=cls.employee1_2, shop=cls.shop1, function_group=cls.group1, norm_work_hours=50,
            work_types__work_type=cls.work_type1_cleaner,
        )
        cls.employment2_1_2 = EmploymentFactory(
            employee=cls.employee2_1, shop=cls.shop2, function_group=cls.group1,
            work_types__work_type=cls.work_type2_cachier,
        )
        cls.employment2_2_3 = EmploymentFactory(
            employee=cls.employee2_2, shop=cls.shop3, function_group=cls.group1, norm_work_hours=50,
            work_types__work_type=cls.work_type3_cachier,
        )
        cls.employment3 = EmploymentFactory(
            employee=cls.employee3, shop=cls.shop3, function_group=cls.group2,
            work_types__work_type=cls.work_type3_cachier,
        )
        cls.dt = timezone.now().date()
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

    def _make_tick_requests(self, user, shop, dttm_coming=None, dttm_leaving=None):
        # TODO: разобраться с таймзонами
        self.client.force_authenticate(user=user)

        with mock.patch('src.recognition.views.now') as _now_mock:
            _now_mock.return_value = (
                        dttm_coming - timedelta(hours=shop.get_tz_offset())) if dttm_coming else timezone.now()
            resp_coming = self.client.post(
                self.get_url('Tick-list'),
                data=self.dump_data({
                    'type': Tick.TYPE_COMING,
                    'shop_code': shop.code,
                }),
                content_type='application/json',
            )
        self.assertEqual(resp_coming.status_code, status.HTTP_200_OK)

        with mock.patch('src.recognition.views.now') as _now_mock:
            _now_mock.return_value = (
                        dttm_leaving - timedelta(hours=shop.get_tz_offset())) if dttm_leaving else timezone.now()
            resp_leaving = self.client.post(
                self.get_url('Tick-list'),
                data=self.dump_data({
                    'type': Tick.TYPE_LEAVING,
                    'shop_code': shop.code,
                }),
                content_type='application/json',
            )
        self.assertEqual(resp_leaving.status_code, status.HTTP_200_OK)

        fact_approved_list = list(WorkerDay.objects.filter(
            employee__user=user,
            dt=self.dt,
            is_fact=True,
            is_approved=True,
        ))
        self.assertNotEqual(len(fact_approved_list), 0)
        return fact_approved_list

    def test_get_employment_from_plan(self):
        """
        Получение трудоустройства из плана
        """
        self.client.force_authenticate(user=self.user1)
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee1_2,
            employment=self.employment1_2_1,
            shop=self.shop1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        fact_approved_list = self._make_tick_requests(
            self.user1, self.shop1,
            dttm_coming=datetime.combine(self.dt, time(8, 53, 0)),
            dttm_leaving=datetime.combine(self.dt, time(21, 15, 0)),
        )
        self.assertEqual(len(fact_approved_list), 1)
        fact_approved = fact_approved_list[0]
        self.assertEqual(fact_approved.employment_id, self.employment1_2_1.id)
        self.assertIsNotNone(fact_approved.dttm_work_start)
        self.assertIsNotNone(fact_approved.dttm_work_end)

    def test_get_employment_for_user2_by_shop2(self):
        """
        Получение трудоустройства с приоритетом по подразделению в случае если нету плана (shop2)
        """
        self.client.force_authenticate(user=self.user2)
        fact_approved_list = self._make_tick_requests(self.user2, self.shop2)
        self.assertEqual(len(fact_approved_list), 1)
        fact_approved = fact_approved_list[0]
        self.assertEqual(fact_approved.employment_id, self.employment2_1_2.id)

    def test_get_employment_for_user2_by_shop3(self):
        """
        Получение трудоустройства с приоритетом по подразделению в случае если нету плана (shop3)
        """
        self.client.force_authenticate(user=self.user2)
        fact_approved_list = self._make_tick_requests(self.user2, self.shop3)
        self.assertEqual(len(fact_approved_list), 1)
        fact_approved = fact_approved_list[0]
        self.assertEqual(fact_approved.employment_id, self.employment2_2_3.id)

    # падает в 00:20+
    def test_get_employment_by_max_norm_work_hours_when_multiple_active_empls_in_the_same_shop(self):
        """
        Получение трудоустройства с наибольшей ставкой
        """
        self.client.force_authenticate(user=self.user1)
        fact_approved_list = self._make_tick_requests(self.user1, self.shop1)
        self.assertEqual(len(fact_approved_list), 1)
        fact_approved = fact_approved_list[0]
        self.assertEqual(fact_approved.employment_id, self.employment1_1_1.id)

    def test_multiple_wdays_for_the_same_user_in_the_same_shop(self):
        """
        2 рабочих дня под разными Сотрудниками у 1 Пользователя в одном Подразделении

        В плане
        1 рабочий день с 09:00 до 15:00
        2 рабочий день с 15:01 до 20:00

        Если сотрудник закончит по 1 смене чуть раньше в 14:40 и переоткроет смену,
        то должны привязаться к началу следующего дня
        """
        self.client.force_authenticate(user=self.user1)
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee1_1,
            employment=self.employment1_1_1,
            shop=self.shop1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(15, 0, 0)),
        )
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee1_2,
            employment=self.employment1_2_1,
            shop=self.shop1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(15, 0, 1)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )

        fact_approved1_list = self._make_tick_requests(
            self.user1, self.shop1,
            dttm_coming=datetime.combine(self.dt, time(8, 53, 0)),
            dttm_leaving=datetime.combine(self.dt, time(14, 41, 0)),
        )
        self.assertEqual(len(fact_approved1_list), 1)
        fact_approved1 = fact_approved1_list[0]
        self.assertEqual(fact_approved1.employment_id, self.employment1_1_1.id)
        self.assertEqual(fact_approved1.dttm_work_start, datetime.combine(self.dt, time(8, 53, 0)))
        self.assertEqual(fact_approved1.dttm_work_end, datetime.combine(self.dt, time(14, 41, 0)))

        fact_approved2_list = self._make_tick_requests(
            self.user1, self.shop1,
            dttm_coming=datetime.combine(self.dt, time(14, 42, 0)),
            dttm_leaving=datetime.combine(self.dt, time(19, 57, 0)),
        )
        self.assertEqual(len(fact_approved2_list), 2)
        fact_approved2_list = list(filter(lambda i: i.id != fact_approved1.id, fact_approved2_list))
        self.assertEqual(len(fact_approved2_list), 1)
        fact_approved2 = fact_approved2_list[0]
        self.assertEqual(fact_approved2.employment_id, self.employment1_2_1.id)
        self.assertEqual(fact_approved2.dttm_work_start, datetime.combine(self.dt, time(14, 42, 0)))
        self.assertEqual(fact_approved2.dttm_work_end, datetime.combine(self.dt, time(19, 57, 0)))


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, TRUST_TICK_REQUEST=True)
class TestConfirmVacancy(MultipleActiveEmploymentsSupportMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(TestConfirmVacancy, cls).setUpTestData()
        cls.dt_now = date.today()
        cls.add_group_perm(cls.group1, 'WorkerDay_confirm_vacancy', 'POST')
        for employee in [cls.employee1_1, cls.employee1_2, cls.employee2_1, cls.employee2_2]:
            WorkerDayFactory(
                dt=cls.dt_now,
                employee=employee,
                is_fact=False,
                is_approved=True,
                type_id=WorkerDay.TYPE_HOLIDAY,
            )

    def test_empl_received_by_cashier_work_type(self):
        vacancy = WorkerDayFactory(
            employee=None,
            employment=None,
            shop=self.shop1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            is_vacancy=True,
            is_fact=False,
            is_approved=True,
            cashbox_details__work_type=self.work_type1_cachier,
        )
        WorkerDay.check_work_time_overlap(employee_id=self.employee1_1.id)
        self.client.force_authenticate(user=self.user1)
        resp = self.client.post(self.get_url('WorkerDay-confirm-vacancy', pk=vacancy.pk))
        self.assertEqual(resp.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employment_id, self.employment1_1_1.id)

    def test_empl_received_by_cleaner_work_type(self):
        vacancy = WorkerDayFactory(
            employee=None,
            employment=None,
            shop=self.shop1,
            type_id=WorkerDay.TYPE_WORKDAY,
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
        self.assertEqual(vacancy.employment_id, self.employment1_2_1.id)

    def test_empl_received_by_shop_if_no_equal_work_type(self):
        vacancy = WorkerDayFactory(
            employee=None,
            employment=None,
            shop=self.shop3,
            type_id=WorkerDay.TYPE_WORKDAY,
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
        self.assertEqual(vacancy.employment_id, self.employment2_2_3.id)


class TestGetWorkersStatAndTabel(MultipleActiveEmploymentsSupportMixin, APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        super(TestGetWorkersStatAndTabel, cls).setUpTestData()
        cls.dt_now = date.today()
        cls.add_group_perm(cls.group1, 'WorkerDay', 'GET')
        cls.add_group_perm(cls.group1, 'WorkerDay_worker_stat', 'GET')

    def _create_wdays(self, dt_now):
        for dt in pd.date_range(dt_now, dt_now + timedelta(days=4)).date:
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_1,
                employment=self.employment1_1_1,
                shop=self.shop1,
                type_id=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type1_cachier,
            )

        for dt in pd.date_range(dt_now + timedelta(days=5), dt_now + timedelta(days=9)).date:
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_1,
                employment=self.employment1_1_1,
                shop=self.shop1,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_fact=False,
                is_approved=True,
            )
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_2,
                employment=self.employment1_2_1,
                shop=self.shop1,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_fact=False,
                is_approved=True,
            )

        for dt in pd.date_range(dt_now + timedelta(days=10), dt_now + timedelta(days=14)).date:
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_2,
                employment=self.employment1_2_1,
                shop=self.shop1,
                type_id=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type1_cleaner,
            )

        for dt in pd.date_range(dt_now + timedelta(days=15), dt_now + timedelta(days=19)).date:
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_1,
                employment=self.employment1_1_1,
                shop=self.shop1,
                type_id=WorkerDay.TYPE_VACATION,
                is_fact=False,
                is_approved=True,
            )
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_2,
                employment=self.employment1_2_1,
                shop=self.shop1,
                type_id=WorkerDay.TYPE_VACATION,
                is_fact=False,
                is_approved=True,
            )

        for dt in pd.date_range(dt_now + timedelta(days=20), dt_now + timedelta(days=24)).date:
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_2,
                employment=self.employment1_2_1,
                shop=self.shop1,
                type_id=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type1_cleaner,
            )

    def test_get_tabel_data_by_tabel_code(self):
        """
        Проверка получения дней по табельному номеру Сотрудника
        """
        self._create_wdays(self.dt_now)
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(
            self.get_url('WorkerDay-list'),
            data={
                'dt__gte': self.dt_now,
                'dt__lte': self.dt_now + timedelta(days=24),
                'fact_tabel': True,
                'employment__tabel_code__in': 'employee1_1',
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
                'employment__tabel_code__in': 'employee1_2',
            },
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 20)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_WORKDAY, resp_data))), 10)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_HOLIDAY, resp_data))), 5)
        self.assertEqual(len(list(filter(lambda i: i['type'] == WorkerDay.TYPE_VACATION, resp_data))), 5)

    def test_fact_tabel_data_by_fact_shop_code__in_filter(self):
        self._create_wdays(self.dt_now)
        for dt in pd.date_range(self.dt_now + timedelta(days=25), self.dt_now + timedelta(days=28)).date:
            WorkerDayFactory(
                dt=dt,
                employee=self.employee1_1,
                employment=self.employment1_1_1,
                shop=self.shop3,
                type_id=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type3_cachier,
            )
        for dt in pd.date_range(self.dt_now + timedelta(days=25), self.dt_now + timedelta(days=28)).date:
            WorkerDayFactory(
                dt=dt,
                employee=self.employee2_2,
                employment=self.employment2_2_3,
                shop=self.shop3,
                type_id=WorkerDay.TYPE_WORKDAY,
                is_fact=True,
                is_approved=True,
                cashbox_details__work_type=self.work_type3_cachier,
            )
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(
            self.get_url('WorkerDay-list'),
            data={
                'dt__gte': self.dt_now,
                'dt__lte': self.dt_now + timedelta(days=28),
                'fact_tabel': True,
                'fact_shop_code__in': [self.shop3.code],
                'by_code': True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 23)
        self.assertEqual(len(list(
            filter(lambda i: i['type'] == WorkerDay.TYPE_WORKDAY and i['employee_id'] == self.employee1_1.id and i[
                'shop_id'] == self.shop1.id,
                   resp_data))), 5)
        self.assertEqual(len(list(
            filter(lambda i: i['type'] == WorkerDay.TYPE_WORKDAY and i['employee_id'] == self.employee1_1.id and i[
                'shop_id'] == self.shop3.id,
                   resp_data))), 4)
        self.assertEqual(len(list(
            filter(lambda i: i['type'] == WorkerDay.TYPE_HOLIDAY and i['employee_id'] == self.employee1_1.id,
                   resp_data))), 5)
        self.assertEqual(len(list(
            filter(lambda i: i['type'] == WorkerDay.TYPE_VACATION and i['employee_id'] == self.employee1_1.id,
                   resp_data))), 5)
        self.assertEqual(len(list(
            filter(lambda i: i['type'] == WorkerDay.TYPE_WORKDAY and i['employee_id'] == self.employee2_2.id and i[
                'shop_id'] == self.shop3.id,
                   resp_data))), 4)

    def test_get_worker_stat_by_employee(self):
        """
        Проверка возможности получения статистики по сотруднику
        """
        self._create_wdays(date(2021, 3, 1))
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(
            self.get_url('WorkerDay-worker-stat'),
            data={
                'dt_from': date(2021, 3, 1),
                'dt_to': date(2021, 3, 31),
                'shop_id': self.shop1.id,
                'employee_id__in': f'{self.employee1_1.id},{self.employee1_2.id}',
            },
        )
        resp_data = resp.json()
        employee1_1_data = resp_data.get(str(self.employee1_1.id))
        employee1_1_data.pop('employments', None)
        self.assertDictEqual(
            employee1_1_data,
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
                            "curr_month_end": 144.0,
                            "selected_period": 144.0,
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
                        "work_hours": {
                            "prev_months": 0,
                            "acc_period": 0
                        },
                        "norm_hours": {
                            "acc_period": 144.0,
                            "prev_months": 0.0,
                            "curr_month": 144.0,
                            "curr_month_end": 144.0,
                            "selected_period": 144.0,
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
                        "day_type": {
                            "H": 5,
                            "V": 5
                        },
                        "workdays_count_outside_of_selected_period": {
                            "3": 0
                        },
                        "any_day_count_outside_of_selected_period": {
                            "3": 0
                        },
                        "norm_hours": {
                            "acc_period": 144.0,
                            "prev_months": 0.0,
                            "curr_month": 144.0,
                            "curr_month_end": 144.0,
                            "selected_period": 144.0,
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
                        "work_hours": {
                            "prev_months": 0,
                            "acc_period": 0
                        },
                        "norm_hours": {
                            "acc_period": 176.0,
                            "prev_months": 0.0,
                            "curr_month": 176.0,
                            "curr_month_end": 176.0,
                            "selected_period": 176.0,
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
        employee1_2_data = resp_data.get(str(self.employee1_2.id))
        employee1_2_data.pop('employments', None)
        self.assertDictEqual(
            employee1_2_data,
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
                            "curr_month_end": 72.0,
                            "selected_period": 72.0,
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
                        "work_hours": {
                            "prev_months": 0,
                            "acc_period": 0
                        },
                        "norm_hours": {
                            "acc_period": 72.0,
                            "prev_months": 0.0,
                            "curr_month": 72.0,
                            "curr_month_end": 72.0,
                            "selected_period": 72.0,
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
                        "day_type": {
                            "H": 5,
                            "V": 5
                        },
                        "workdays_count_outside_of_selected_period": {
                            "3": 0
                        },
                        "any_day_count_outside_of_selected_period": {
                            "3": 0
                        },
                        "norm_hours": {
                            "acc_period": 72.0,
                            "prev_months": 0.0,
                            "curr_month": 72.0,
                            "curr_month_end": 72.0,
                            "selected_period": 72.0,
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
                        "work_hours": {
                            "prev_months": 0,
                            "acc_period": 0
                        },
                        "norm_hours": {
                            "acc_period": 88.0,
                            "prev_months": 0.0,
                            "curr_month": 88.0,
                            "curr_month_end": 88.0,
                            "selected_period": 88.0,
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


class TestWorkTimeOverlap(MultipleActiveEmploymentsSupportMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.add_group_perm(cls.group1, 'WorkerDay', 'POST')
        GroupWorkerDayPermission.objects.bulk_create(
            GroupWorkerDayPermission(
                group=cls.group1,
                worker_day_permission=wdp,
            ) for wdp in WorkerDayPermission.objects.all()
        )

    def test_time_of_workdays_for_one_user_should_not_overlap(self):
        """
        При создании/изменении рабочего дня должна происходить проверка пересечения времени сотрудника
        """
        WorkerDayFactory(
            is_fact=False,
            is_approved=False,
            dt=self.dt,
            employee=self.employee1_1,
            employment=self.employment1_2_1,
            shop=self.shop1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(17, 0, 0)),
        )

        new_wd_data = {
            "shop_id": self.shop1.id,
            "employee_id": self.employee1_2.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(16, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(22, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type1_cleaner.id}
            ]
        }

        self.client.force_authenticate(user=self.user1)
        resp = self.client.post(
            self.get_url('WorkerDay-list'),
            data=self.dump_data(new_wd_data),
            content_type='application/json',
        )
        self.assertContains(
            resp, 'Операция не может быть выполнена. Недопустимое пересечение времени работы.', status_code=400)

        new_wd_data['dttm_work_start'] = datetime.combine(self.dt, time(17, 0, 0))

        resp = self.client.post(
            self.get_url('WorkerDay-list'),
            data=self.dump_data(new_wd_data),
            content_type='application/json',
        )

        self.assertEqual(resp.status_code, 201)


class TestEmployeeAPI(MultipleActiveEmploymentsSupportMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.add_group_perm(cls.group1, 'Employee', 'GET')
        cls.add_group_perm(cls.group1, 'Employee', 'PUT')
        cls.add_group_perm(cls.group1, 'Employee', 'POST')

    def test_get_employee_with_employments(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(
            self.get_url('Employee-list'), data={'include_employments': True, 'show_constraints': True})
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 5)
        employee_data = resp_data[0]
        self.assertIn('employments', employee_data)
        employment_data = employee_data['employments'][0]
        self.assertIn('worker_constraints', employment_data)

    def test_get_employee_without_employments(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(self.get_url('Employee-list'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 5)
        employee_data = resp_data[0]
        self.assertNotIn('employments', employee_data)

    def test_can_update_tabel_code_by_employee_id(self):
        self.client.force_authenticate(user=self.user1)
        new_tabel_code = 'new_tabel_code'
        resp = self.client.put(
            self.get_url('Employee-detail', pk=self.employee1_1.id),
            data=self.dump_data({'tabel_code': new_tabel_code}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Employee.objects.get(id=self.employee1_1.id).tabel_code, new_tabel_code)

    def test_can_create_employee_without_tabel_code(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.post(
            self.get_url('Employee-list'),
            data=self.dump_data({'user_id': self.user1.id}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        e = Employee.objects.get(id=resp.json()['id'])
        self.assertEqual(e.user_id, self.user1.id)
        self.assertEqual(e.tabel_code, None)

    def test_can_filter_by_group_id(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get(
            self.get_url('Employee-list'),
            data={'group_id__in': str(self.group2.id)},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['id'], self.employee3.id)

    def test_get_attendance_records_report(self):
        from src.timetable.models import AttendanceRecords
        coming_time = time(10)
        leaving_time = time(20)
        AttendanceRecords.objects.create(
            shop=self.shop1,
            type=AttendanceRecords.TYPE_COMING,
            user=self.user1,
            dttm=datetime.combine(self.dt, coming_time),
        )
        AttendanceRecords.objects.create(
            shop=self.shop1,
            type=AttendanceRecords.TYPE_LEAVING,
            user=self.user1,
            dttm=datetime.combine(self.dt, leaving_time),
        )
        AttendanceRecords.objects.create(
            shop=self.shop2,
            type=AttendanceRecords.TYPE_COMING,
            user=self.user2,
            dttm=datetime.combine(self.dt, coming_time),
        )
        AttendanceRecords.objects.create(
            shop=self.shop2,
            type=AttendanceRecords.TYPE_LEAVING,
            user=self.user2,
            dttm=datetime.combine(self.dt, leaving_time),
        )
        self.client.force_authenticate(user=self.user1)
        self.add_group_perm(self.group1, 'AttendanceRecords_report', 'GET')
        resp = self.client.get(self.get_url('AttendanceRecords-report'))
        BytesIO = pd.io.common.BytesIO
        df = pd.read_excel(BytesIO(resp.content), engine='xlrd')
        self.assertEqual(len(df.index), 4)

        resp = self.client.get(
            self.get_url('AttendanceRecords-report'), data={'employee_id__in': [self.employee1_1.id]})
        BytesIO = pd.io.common.BytesIO
        df = pd.read_excel(BytesIO(resp.content), engine='xlrd')
        self.assertEqual(len(df.index), 2)

        resp = self.client.get(
            self.get_url('AttendanceRecords-report'), data={'shop_id__in': [self.shop1.id]})
        BytesIO = pd.io.common.BytesIO
        df = pd.read_excel(BytesIO(resp.content), engine='xlrd')
        self.assertEqual(len(df.index), 2)

        resp = self.client.get(
            self.get_url('AttendanceRecords-report'),
            data={
                'shop_id__in': [self.shop1.id],
                'employee_id__in': [self.employee2_1.id]
            })
        BytesIO = pd.io.common.BytesIO
        df = pd.read_excel(BytesIO(resp.content), engine='xlrd')
        self.assertEqual(len(df.index), 0)

    def test_other_deps_employees_with_wd_in_curr_shop_parameter(self):
        self.client.force_authenticate(user=self.user1)
        WorkerDayFactory(
            is_fact=False,
            is_approved=False,
            dt=self.dt,
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(17, 0, 0)),
        )

        resp = self.client.get(self.get_url('Employee-list'), data={
            'shop_id': self.shop1.id,
            'employments__dt_from': self.dt.replace(day=1),
            'employments__dt_to': (self.dt + relativedelta(months=1)).replace(day=1) - timedelta(days=1),
            'other_deps_employees_with_wd_in_curr_shop': True,
        })
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 3)
        self.assertTrue(any(self.employee3.id == d['id'] for d in resp_data))
        employee1_1_data = list(filter(lambda i: i['id'] == self.employee1_1.id, resp_data))[0]
        self.assertTrue(employee1_1_data['has_shop_employment'])
        employee3_data = list(filter(lambda i: i['id'] == self.employee3.id, resp_data))[0]
        self.assertFalse(employee3_data['has_shop_employment'])
