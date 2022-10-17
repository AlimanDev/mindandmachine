import json
from datetime import timedelta, time, datetime, date
from unittest import mock

from dateutil.relativedelta import relativedelta
from django.db import transaction
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import (
    Network,
    Employment,
    Shop,
    User,
    NetworkConnect,
)
from src.timetable.models import (
    WorkerDay,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    WorkerDayPermission,
    GroupWorkerDayPermission,
    WorkerDayType,
    ExchangeSettings,
)
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter


class TestAditionalFunctions(TestsHelperMixin, APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/worker_day/'
        cls.create_departments_and_users()
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop)
        ExchangeSettings.objects.create(network=cls.network)

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def update_or_create_holidays(self, employment, dt_from, count, approved, wds={}):
        result = {}
        for day in range(count):
            dt = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(dt, None)
            result[dt] = WorkerDay.objects.create(
                employee=employment.employee,
                employment=employment,
                shop=None,
                dt=dt,
                type_id=WorkerDay.TYPE_HOLIDAY,
                is_approved=approved,
                parent_worker_day=parent_worker_day,
            )
        return result

    def create_worker_days(self, employment, dt_from, count, from_tm, to_tm, approved, wds={}, is_blocked=False, night_shift=False, shop_id=None):
        result = {}
        for day in range(count):
            date = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(date, None)
            date_to = date + timedelta(1) if night_shift else date
            wd = WorkerDay.objects.create(
                employment=employment,
                employee=employment.employee,
                shop_id=shop_id or employment.shop_id,
                dt=date,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(date, time(from_tm)),
                dttm_work_end=datetime.combine(date_to, time(to_tm)),
                is_approved=approved,
                parent_worker_day=parent_worker_day,
                is_blocked=is_blocked,
                is_vacancy=employment.shop_id != shop_id if shop_id else False,
            )
            result[date] = wd

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        return result

    def test_delete_worker_days(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 6, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 6, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 4, 16, 20, False)
        self.create_worker_days(self.employment2, dt_from + timedelta(4), 1, 16, 20, False, shop_id=self.shop2.id)
        self.create_worker_days(self.employment3, dt_from, 6, 10, 21, False)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(5), 1, False)

        url = f'{self.url}delete_worker_days/'
        data = {
            'employee_ids':[self.employment2.employee_id, self.employment3.employee_id],
            'dates': [
                dt_from + timedelta(i)
                for i in range(5)
            ]
        }
        with mock.patch.object(WorkerDay, '_check_delete_single_wd_data_perm') as _check_delete_single_wd_data_perm:
            response = self.client.post(url, data, format='json')
            self.assertEqual(_check_delete_single_wd_data_perm.call_count, 5)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 12)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 2)

    def test_delete_exclude_other_shops(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 2, 16, 20, False)
        self.create_worker_days(self.employment2, dt_from + timedelta(2), 1, 16, 20, False, shop_id=self.shop2.id)
        self.create_worker_days(self.employment3, dt_from, 2, 10, 21, False)
        self.create_worker_days(self.employment3, dt_from + timedelta(2), 2, 10, 21, False, shop_id=self.shop2.id)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(3), 1, False)

        url = f'{self.url}delete_worker_days/'
        data = {
            'employee_ids':[self.employment2.employee_id, self.employment3.employee_id],
            'dates':[
                dt_from + timedelta(i)
                for i in range(3)
            ],
            'shop_id': self.shop.id,
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, shop_id=self.shop.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, shop_id=self.shop2.id).count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, shop_id=None).count(), 1)
    
    def test_delete_fact(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 3, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        WorkerDay.objects.all().update(is_fact=True)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(3), 1, False)

        url = f'{self.url}delete_worker_days/'
        data = {
            'employee_ids': [self.employment2.employee_id, self.employment3.employee_id],
            'dates': [
                dt_from + timedelta(i)
                for i in range(3)
            ]
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 8)

        data['is_fact'] = True
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 2)

    def test_exchange_approved(self):
        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(response.json()[0]['is_approved'], True)
        self.assertEqual(WorkerDay.objects.count(), 8)
        self.assertEqual(WorkerDay.objects.filter(source=WorkerDay.SOURCE_EXCHANGE_APPROVED).count(), 8)

    def test_cant_exchange_approved_and_protected_without_perm(self):
        dt_from = date.today()
        dates = [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)]
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': dates,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True, is_blocked=True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True, is_blocked=True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 403)
        dates_str = ','.join(dates)
        self.assertEqual(
            response.json()['detail'],
            'У вас нет прав на подтверждение защищенных рабочих дней ('
            f'{self.user2.last_name} {self.user2.first_name} ({self.user2.username}): {dates_str}, '
            f'{self.user3.last_name} {self.user3.first_name} ({self.user3.username}): {dates_str}'
            '). Обратитесь, пожалуйста, к администратору системы.',
        )

    def test_can_exchange_approved_and_protected_with_perm(self):
        self.admin_group.has_perm_to_change_protected_wdays = True
        self.admin_group.save()

        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True, is_blocked=True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True, is_blocked=True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(response.json()[0]['is_approved'], True)
        self.assertEqual(WorkerDay.objects.count(), 8)

    def test_doctors_schedule_send_on_exchange_approved(self):
        with self.settings(SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE=True, CELERY_TASK_ALWAYS_EAGER=True):
            from src.celery.tasks import send_doctors_schedule_to_mis
            with mock.patch.object(send_doctors_schedule_to_mis, 'delay') as send_doctors_schedule_to_mis_delay:
                dt_from = date.today()
                data = {
                    'employee1_id': self.employee2.id,
                    'employee2_id': self.employee3.id,
                    'dates': [
                        Converter.convert_date(dt_from + timedelta(i)) for i in range(-2, 4)
                    ],
                }
                # другой тип работ -- не отправляется
                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from - timedelta(days=2), is_approved=True,
                    cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                    cashbox_details__work_type__work_type_name__code='consult',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from - timedelta(days=2), is_approved=True,
                )

                wd_create_user3_and_delete_user2 = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from - timedelta(days=1), is_approved=True,
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from - timedelta(days=1), is_approved=True,
                )

                wd_update_user3 = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from, is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                wd_update_user2 = WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from, is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(20, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )

                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from + timedelta(days=1), is_approved=True,
                )
                wd_create_user2_and_delete_user3 = WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=1), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(11, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )

                # не рабочие дни -- не отправляется
                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from + timedelta(days=2), is_approved=True,
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_VACATION, shop=self.shop, dt=dt_from + timedelta(days=2), is_approved=True,
                )

                wd_create_user3_and_delete_user2_diff_work_types = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=3), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from + timedelta(days=3), time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from + timedelta(days=3), time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type_id=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=3), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from + timedelta(days=3), time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from + timedelta(days=3), time(20, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                    cashbox_details__work_type__work_type_name__code='consult',
                )

                with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                    url = f'{self.url}exchange_approved/'
                    response = self.client.post(url, data, format='json')
                send_doctors_schedule_to_mis_delay.assert_called_once()
                json_data = json.loads(send_doctors_schedule_to_mis_delay.call_args[1]['json_data'])
                self.assertListEqual(
                    sorted(json_data, key=lambda i: (i['dt'], i['employee__user__username'])),
                    sorted([
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_end),
                            "action": "delete"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2.dttm_work_end),
                            "action": "create"
                        },
                        {
                            "dt": Converter.convert_date(wd_update_user2.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_update_user2.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_update_user2.dttm_work_end),
                            "action": "update"
                        },
                        {
                            "dt": Converter.convert_date(wd_update_user3.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_update_user3.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_update_user3.dttm_work_end),
                            "action": "update"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user2_and_delete_user3.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_end),
                            "action": "create"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user2_and_delete_user3.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user2_and_delete_user3.dttm_work_end),
                            "action": "delete"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2_diff_work_types.dt),
                            "employee__user__username": "user2",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_end),
                            "action": "delete"
                        },
                        {
                            "dt": Converter.convert_date(wd_create_user3_and_delete_user2_diff_work_types.dt),
                            "employee__user__username": "user3",
                            "shop__code": self.shop.code,
                            "dttm_work_start": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_start),
                            "dttm_work_end": Converter.convert_datetime(wd_create_user3_and_delete_user2_diff_work_types.dttm_work_end),
                            "action": "create"
                        },
                    ], key=lambda i: (i['dt'], i['employee__user__username']))
                )

                self.assertEqual(len(response.json()), 12)
                self.assertEqual(WorkerDay.objects.count(), 12)

    def test_exchange_with_holidays(self):
        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(2)],
        }
        self.create_worker_days(self.employment2, dt_from, 1, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from + timedelta(1), 1, 9, 21, True)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(1), 1, True)
        self.update_or_create_holidays(self.employment3, dt_from, 1, True)
        url = f'{self.url}exchange_approved/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 4)
        employment3_worker_day = list(filter(lambda x: x['employment_id'] == self.employment3.id and x['type'] == WorkerDay.TYPE_WORKDAY, data))[0]
        self.assertEqual(employment3_worker_day['shop_id'], self.employment3.shop.id)
        self.assertEqual(employment3_worker_day['work_hours'], '08:45:00')
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_HOLIDAY, dt=dt_from, is_approved=True, employment=self.employment2).exists())
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_WORKDAY, dt=dt_from + timedelta(1), is_approved=True, employment=self.employment2).exists())
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_WORKDAY, dt=dt_from, is_approved=True, employment=self.employment3).exists())
        self.assertTrue(WorkerDay.objects.filter(type_id=WorkerDay.TYPE_HOLIDAY, dt=dt_from + timedelta(1), is_approved=True, employment=self.employment3).exists())

    def test_exchange_not_approved(self):
        dt_from = date.today()
        data = {
            'employee1_id': self.employee2.id,
            'employee2_id': self.employee3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 4, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        url = f'{self.url}exchange/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.count(), 16)
        self.assertEqual(WorkerDay.objects.filter(source=WorkerDay.SOURCE_EXCHANGE, is_approved=False).count(), 8)

    def test_duplicate_full(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False, source=WorkerDay.SOURCE_DUPLICATE).count(), 5)

    def test_duplicate_less(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 4)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 5)

    def test_duplicate_more(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(10)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(8)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)

    def test_duplicate_for_different_start_dates(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)

    def test_duplicate_day_without_time(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)
        self.update_or_create_holidays(self.employment2, dt_from, 1, False)

        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(1)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)

    def test_cant_duplicate_when_there_is_no_active_employment(self):
        dt_from = date.today()
        dt_from2 = dt_from + timedelta(days=10)

        Employment.objects.filter(id=self.employment3.id).update(
            dt_hired=dt_from - timedelta(days=30),
            dt_fired=dt_from2,
        )

        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()[0],
            'Невозможно создать дни в выбранные даты. Пожалуйста, '
            'проверьте наличие активного трудоустройства у сотрудника.'
        )
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 0)

    def test_duplicate_night_shifts(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 20, 10, True, night_shift=True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 5)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False, work_hours__gt=timedelta(0)).count(), 5)
        wd = WorkerDay.objects.filter(employee=self.employee3, is_approved=False).order_by('dt').first()
        self.assertEqual(wd.dttm_work_start, datetime.combine(dt_from, time(20)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(dt_from + timedelta(1), time(10)))

    def test_the_order_of_days_is_determined_by_day_date_not_by_the_date_of_creation(self):
        dt_now = date.today()
        dt_tomorrow = dt_now + timedelta(days=1)
        dt_to = dt_now + timedelta(days=5)

        wd_dt_tomorrow = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt_tomorrow,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt_now, time(8, 0, 0)),
            dttm_work_end=datetime.combine(dt_now, time(20, 0, 0)),
            is_fact=False,
            is_approved=False,
        )
        wd_dt_now = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt_now,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_fact=False,
            is_approved=False,
        )

        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [wd_dt_now.dt, wd_dt_tomorrow.dt],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_to + timedelta(days=i)) for i in range(2)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee3, is_approved=False, dt=dt_to, type='H'
        ).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee3, is_approved=False, dt=dt_to + timedelta(days=1), type_id='W'
        ).count(), 1)

    def test_copy_approved(self):
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        self.update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        WorkerDay.objects.create(
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=True,
            dt=dt_now + timedelta(1),
        )
        self.create_worker_days(self.employment2, dt_now, 5, 10, 20, True)
        self.update_or_create_holidays(self.employment2, dt_now + timedelta(days=5), 2, True)
        self.create_worker_days(self.employment3, dt_now, 4, 10, 20, True)
        self.update_or_create_holidays(self.employment3, dt_now + timedelta(days=4), 2, True)

        data = {
            'employee_ids': [
                self.employment1.employee_id,
                self.employment3.employee_id,
            ],
            'dates': [
                dt_now + timedelta(days=i)
                for i in range(6)
            ]
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 12)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, source=WorkerDay.SOURCE_COPY_APPROVED_PLAN_TO_PLAN).count(), 12)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)
    
    def test_copy_approved_when_approved_not_exists(self):
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, False)

        data = {
            'employee_ids': [
                self.employment1.employee_id,
            ],
            'dates': [
                dt_now + timedelta(days=i)
                for i in range(6)
            ]
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 3)
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)

    def test_copy_approved_to_fact(self):
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        self.update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        self.create_worker_days(self.employment2, dt_now, 5, 10, 20, True)
        self.update_or_create_holidays(self.employment2, dt_now + timedelta(days=5), 2, True)
        self.create_worker_days(self.employment3, dt_now, 4, 10, 20, True)
        self.update_or_create_holidays(self.employment3, dt_now + timedelta(days=4), 2, True)
        WorkerDay.objects.create(
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            dt=dt_now,
            type_id=WorkerDay.TYPE_EMPTY,
            shop_id=self.employment1.shop_id,
            is_fact=True,
        )
        data = {
            'employee_ids': [
                self.employment1.employee_id,
                self.employment3.employee_id,
            ],
            'dates': [
                dt_now + timedelta(days=i)
                for i in range(6)
            ],
            'type': 'PF',
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 1)
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 7)
        self.assertEqual(WorkerDay.objects.filter(
            is_approved=False, is_fact=True, work_hours__gt=timedelta(seconds=0), source=WorkerDay.SOURCE_COPY_APPROVED_PLAN_TO_FACT).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, type_id=WorkerDay.TYPE_HOLIDAY).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)

    def test_copy_approved_fact_to_fact(self):
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        self.update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        self.create_worker_days(self.employment2, dt_now, 5, 10, 20, True)
        self.update_or_create_holidays(self.employment2, dt_now + timedelta(days=5), 2, True)
        self.create_worker_days(self.employment3, dt_now, 4, 10, 20, True)
        self.update_or_create_holidays(self.employment3, dt_now + timedelta(days=4), 2, True)
        WorkerDay.objects.filter(
            type_id=WorkerDay.TYPE_WORKDAY,
        ).update(
            is_fact=True,
        )
        data = {
            'employee_ids': [
                self.employment1.employee_id,
                self.employment3.employee_id,
            ],
            'dates': [
                dt_now + timedelta(days=i)
                for i in range(6)
            ],
            'type': 'FF',
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)
        response = self.client.post(self.url + 'copy_approved/', data=data)

        self.assertEqual(len(response.json()), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, source=WorkerDay.SOURCE_COPY_APPROVED_FACT_TO_FACT).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, type_id=WorkerDay.TYPE_HOLIDAY).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)

    def test_copy_range(self):
        dt_from_first = date.today().replace(day=1)
        dt_from_last = dt_from_first + relativedelta(day=31)
        dt_to_first = dt_from_first + relativedelta(months=1)
        dt_to_last = dt_to_first + relativedelta(day=31)

        for i in range((dt_from_last - dt_from_first).days + 1):
            dt = dt_from_first + timedelta(i)
            type_id = WorkerDay.TYPE_WORKDAY if i % 3 != 0 else WorkerDay.TYPE_HOLIDAY
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment2.shop_id,
                employee_id=self.employment2.employee_id,
                employment=self.employment2,
                type_id=type_id,
                is_approved=True,
            )
            if i % 2 == 0 and i < 28:
                WorkerDay.objects.create(
                    dt=dt,
                    shop_id=self.employment2.shop_id,
                    employee_id=self.employment2.employee_id,
                    employment=self.employment2,
                    type_id=WorkerDay.TYPE_WORKDAY,
                    is_approved=True,
                    is_fact=True,
                )
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment3.shop_id,
                employee_id=self.employment3.employee_id,
                employment=self.employment3,
                type_id=type_id,
                is_approved=True,
            )
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment4.shop_id,
                employee_id=self.employment4.employee_id,
                employment=self.employment4,
                type_id=type_id,
                is_approved=True,
            )

        data = {
            'employee_ids': [
                self.employment2.employee_id,
                self.employment4.employee_id,
            ],
            'from_copy_dt_from': dt_from_first,
            'from_copy_dt_to': dt_from_last,
            'to_copy_dt_from': dt_to_first,
            'to_copy_dt_to': dt_to_last,
            'is_approved': True,
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), ((dt_from_last - dt_from_first).days + 1) * 3 + 14)
        response = self.client.post(self.url + 'copy_range/', data=data)
        response_data = response.json()

        self.assertEqual(len(response_data), ((dt_to_last - dt_to_first).days + 1) * 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, source=WorkerDay.SOURCE_COPY_RANGE).count(), ((dt_to_last - dt_to_first).days + 1) * 2)
        self.assertEqual(
            list(WorkerDay.objects.filter(
                is_fact=False,
                is_approved=False,
                dt__gte=dt_to_first,
                dt__lte=dt_to_last,
            ).order_by(
                'employee__user_id',
            ).values_list(
                'employee__user_id',
                flat=True,
            ).distinct()),
            [self.employment2.employee.user_id, self.employment4.employee.user_id],
        )

    def test_copy_range_types_and_more(self):
        dt_from_first = date.today().replace(day=1)
        dt_from_last = dt_from_first + timedelta(4)
        dt_to_first = dt_from_last + timedelta(1)
        dt_to_last = dt_to_first + timedelta(7)

        for i in range(5):
            # H,W,W,H,W
            dt = dt_from_first + timedelta(i)
            type_id = WorkerDay.TYPE_WORKDAY if i % 3 != 0 else WorkerDay.TYPE_HOLIDAY
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment2.shop_id,
                employee_id=self.employment2.employee_id,
                employment=self.employment2,
                type_id=type_id,
                is_approved=False,
            )
        for i in range(8):
            dt = dt_to_first + timedelta(i)
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment2.shop_id,
                employee_id=self.employment2.employee_id,
                employment=self.employment2,
                type_id=WorkerDay.TYPE_VACATION,
                is_approved=False,
            )

        data = {
            'employee_ids': [
                self.employment2.employee_id,
            ],
            'from_copy_dt_from': dt_from_first,
            'from_copy_dt_to': dt_from_last,
            'to_copy_dt_from': dt_to_first,
            'to_copy_dt_to': dt_to_last,
            'worker_day_types': ['W'],
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 13)
        response = self.client.post(self.url + 'copy_range/', data=data)
        response_data = response.json()

        self.assertEqual(len(response_data), 5)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, type='V').count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, type='W').count(), 5)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last, type='H').count(), 0)

    def test_copy_range_bad_dates(self):
        dt_from_first = date.today().replace(day=1)
        dt_from_last = dt_from_first + relativedelta(day=31)
        dt_to_first = dt_from_first - timedelta(1)
        dt_to_last = dt_to_first + relativedelta(day=31)
        data = {
            'employee_ids': [
                self.employment2.employee_id,
                self.employment4.employee_id,
            ],
            'from_copy_dt_from': dt_from_first,
            'from_copy_dt_to': dt_from_last,
            'to_copy_dt_from': dt_to_first,
            'to_copy_dt_to': dt_to_last,
        }
        response = self.client.post(self.url + 'copy_range/', data=data)
        self.assertEqual(response.json(), ['Начало периода с которого копируются дни не может быть больше начала периода куда копируются дни.'])

    def test_block_worker_day(self):
        dt_now = date.today()
        wd = WorkerDayFactory(
            dt=dt_now,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
            is_fact=True,
        )
        data = {
            'worker_days': [
                {
                    'worker_username': wd.employee.user.username,
                    'shop_code': wd.shop.code,
                    'dt': Converter.convert_date(dt_now),
                    'is_fact': True,
                },
            ]
        }

        response = self.client.post(self.url + 'block/', data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        wd.refresh_from_db()
        self.assertTrue(wd.is_blocked)

    def test_unblock_worker_day(self):
        dt_now = date.today()
        wd = WorkerDayFactory(
            dt=dt_now,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=False,
            is_fact=True,
            is_blocked=True,
        )
        data = {
            'worker_days': [
                {
                    'worker_username': wd.employee.user.username,
                    'shop_code': wd.shop.code,
                    'dt': Converter.convert_date(dt_now),
                    'is_fact': True,
                },
            ]
        }
        response = self.client.post(self.url + 'unblock/', data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        wd.refresh_from_db()
        self.assertFalse(wd.is_blocked)

    def test_batch_block_or_unblock(self):
        self.create_outsource()
        dt = date.today()
        for employment in Employment.objects.get_active(dt_from=dt, dt_to=dt, shop__network=self.network):
            self.create_worker_days(
                employment=employment,
                dt_from=dt - timedelta(5),
                count=5,
                from_tm=9,
                to_tm=18,
                approved=False,
                is_blocked=False
            )
        total = WorkerDay.objects.filter(shop__network=self.network).count() #40
        url = self.url + 'batch_block_or_unblock/'
        
        #Заблокировать все
        data = {
            'dt_from': dt - timedelta(5),
            'dt_to': dt,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json().get('updated'), total)
        
        #Разблокировать все
        data['is_blocked'] = False
        data['shop_ids'] = []
        response = self.client.post(url, data)
        self.assertEqual(response.json().get('updated'), total)
        
        #Период из 1-го дня
        data = {
            'dt_from': dt,
            'dt_to': dt,
            'is_blocked': True
        }
        response = self.client.post(url, data)
        updated = WorkerDay.objects.filter(dt=dt, shop__network=self.network).count() #9
        self.assertEqual(response.json().get('updated'), updated)

        #Заблокировать день у аутсорса сотрудника в магазине основной сети
        wd = WorkerDayFactory(
            shop=self.root_shop,
            employee=self.employee1_outsource,
            employment=self.employment1_outsource,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_blocked=False
        )
        data['is_blocked'] = True
        data['shop_ids'] = [self.root_shop.id]
        response = self.client.post(url, data)
        self.assertEqual(response.json().get('updated'), 1)
        self.assertTrue(WorkerDay.objects.get(id=wd.id, is_blocked=True))

        #Не блокировать нерабочий день у аутсорса сотрудника
        wd = WorkerDayFactory(
            shop=None,
            employee=self.employee1_outsource,
            employment=self.employment1_outsource,
            dt=dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_blocked=False
        )
        del data['shop_ids']
        response = self.client.post(url, data)
        self.assertEqual(response.json().get('updated'), 0)
        self.assertTrue(WorkerDay.objects.get(id=wd.id, is_blocked=False))

        #Заблокировать нерабочий день (по активному трудоустройству в магазине)
        wd = WorkerDayFactory(
            shop=None,
            employee=self.employee1,
            employment=self.employment1,
            dt=dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            is_blocked=False
        )
        response = self.client.post(url, data)
        self.assertEqual(response.json().get('updated'), 1)
        self.assertTrue(WorkerDay.objects.get(id=wd.id, is_blocked=True))

        #Неправильные параметры дат:
        #dt_from > dt_to
        data = {
            'dt_from': dt,
            'dt_to': dt - timedelta(1),
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        #Нельзя изменять дни в будущем
        data = {
            'dt_from': dt + timedelta(1),
            'dt_to': dt + timedelta(100),
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_list_create_vacancy(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
            'outsources': None,
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False, source=WorkerDay.SOURCE_CHANGE_LIST).count(), 10)

    def test_change_list_create_holiday_is_vacancy_setted(self):
        dt_from = date.today()
        data = {
            'type': WorkerDay.TYPE_HOLIDAY,
            'employee_id': self.employee1.id,
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=False, type_id=WorkerDay.TYPE_HOLIDAY, employee_id=self.employee1.id).count(), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, employee_id=self.employee1.id).count(), 0)

    def test_change_list_create_vacancy_with_employee(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'employee_id': self.employee1.id,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False, employee_id=self.employee1.id).count(), 10)
    
    def test_change_list_create_vacancy_with_employee_group_perms(self):
        self.admin_group.subordinates.clear()
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'employee_id': self.employee1.id,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 403)
        self.admin_group.subordinates.add(self.employment1.function_group)
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False, employee_id=self.employee1.id).count(), 10)

    def test_change_list_create_vacancy_with_outsources(self):
        dt_from = date.today()
        outsource_network1 = Network.objects.create(
            name='O1',
        )
        outsource_network2 = Network.objects.create(
            name='O2',
        )
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
            'outsources': [outsource_network1.id, outsource_network2.id],
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=True).count(), 10)
        self.assertCountEqual(
            list(
                WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=True).first().outsources.all()
            ), 
            [outsource_network1, outsource_network2],
        )

    def test_change_list_create_vacancy_weekdays(self):
        dt_from = date(2021, 7, 20)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
            'days_of_week': [0, 3, 6]
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 4)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).count(), 4)
        self.assertEqual(
            list(
                WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).order_by('dt').values_list('dt', flat=True)
            ),
            [date(2021, 7, 22), date(2021, 7, 25), date(2021, 7, 26), date(2021, 7, 29)]
        )

    def test_change_list_create_vacation(self):
        dt_from = date(2021, 1, 1)
        dt_to = date(2021, 1, 31)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_VACATION,
            'dt_from': dt_from,
            'dt_to': dt_to,
            'employee_id': self.employee1.id,
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 31)
        self.assertEqual(WorkerDay.objects.filter(employee_id=self.employee1.id, type_id=WorkerDay.TYPE_VACATION, dt__gte=dt_from, dt__lte=dt_to, source=WorkerDay.SOURCE_CHANGE_LIST).count(), 31)

    def test_change_list_create_multiple_vacs_on_one_date(self):
        dt_from = date(2021, 1, 1)
        dt_to = date(2021, 1, 5)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                },
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_to,
        }
        url = f'{self.url}change_list/'
        self.client.post(url, data, format='json')
        resp = self.client.post(url, data, format='json')
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 5)
        self.assertEqual(
            WorkerDay.objects.filter(
                type_id=WorkerDay.TYPE_WORKDAY, is_vacancy=True, dt__gte=dt_from,
                dt__lte=dt_to, source=WorkerDay.SOURCE_CHANGE_LIST).count(), 10)

    def test_change_list_create_vacancy_many_work_types(self):
        dt_from = date.today()
        work_type_name2 = WorkTypeName.objects.create(name='Магазин2', network=self.network)
        work_type2 = WorkType.objects.create(
            work_type_name=work_type_name2,
            shop=self.shop)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 0.5,
                },
                {
                    'work_type_id': work_type2.id,
                    'work_part': 0.5,
                }
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).count(), 10)
        self.assertEqual(WorkerDayCashboxDetails.objects.count(), 20)

    def test_change_list_create_night_shifts_vacancy(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '20:00:00',
            'tm_work_end': '08:00:00',
            'cashbox_details': [
                {
                    'work_type_id': self.work_type.id,
                    'work_part': 1,
                },
            ],
            'is_vacancy': True,
            'dt_from': dt_from,
            'dt_to': dt_from + timedelta(9),
        }
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 10)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, shop_id=self.shop.id, is_outsource=False).count(), 10)
        wd = WorkerDay.objects.filter(dt=dt_from).first()
        self.assertEqual(wd.dttm_work_start, datetime.combine(dt_from, time(20)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(dt_from + timedelta(1), time(8)))

    def test_change_list_errors(self):
        dt_from = date(2021, 1, 1)
        dt_to = date(2021, 1, 2)
        data = {
            'shop_id': self.shop.id,
            'type': WorkerDay.TYPE_WORKDAY,
            'dt_from': dt_from,
            'dt_to': dt_to,
        }
        url = f'{self.url}change_list/'
        # no tm_start
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'tm_work_start': 'Обязательное поле.'})
        data['tm_work_start'] = '10:00:00'
        # no tm_end
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'tm_work_end': 'Обязательное поле.'})
        data['tm_work_end'] = '20:00:00'
        # no cashbox_details
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'cashbox_details': 'Обязательное поле.'})
        data['cashbox_details'] = [
            {
                'work_type_id': self.work_type.id,
                'work_part': 1,
            }
        ]
        # no employee_id
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'employee_id': 'Обязательное поле.'})
        data['type'] = WorkerDay.TYPE_VACATION
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'employee_id': 'Обязательное поле.'})

    def test_recalc(self):
        today = date.today()
        wd = WorkerDayFactory(
            dt=today,
            type_id=WorkerDay.TYPE_WORKDAY,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.employment2.shop,
            is_approved=True,
            is_fact=True,
            dttm_work_start=datetime.combine(today, time(10)),
            dttm_work_end=datetime.combine(today, time(19)),
        )
        self.assertEqual(wd.work_hours, timedelta(hours=8))
        self.add_group_perm(self.employee_group, 'WorkerDay_recalc', 'POST')

        WorkerDay.objects.filter(id=wd.id).update(work_hours=timedelta(0))
        wd.refresh_from_db()
        self.assertEqual(wd.work_hours, timedelta(0))
        data = {
            'shop_id': wd.employment.shop_id,
            'employee_id__in': [self.employee2.id],
            'dt_from': today,
            'dt_to': today,
        }
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            resp = self.client.post(
                path=self.get_url('WorkerDay-recalc'),
                data=self.dump_data(data), content_type='application/json',
            )
        self.assertContains(resp, 'Пересчет часов успешно запущен.', status_code=200)
        wd.refresh_from_db()
        self.assertEqual(wd.work_hours, timedelta(hours=8))

        data['employee_id__in'] = [self.employee8.id]
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            resp2 = self.client.post(
                path=self.get_url('WorkerDay-recalc'),
                data=self.dump_data(data), content_type='application/json',
            )
        self.assertContains(resp2, 'Не найдено сотрудников удовлетворяющих условиям запроса.', status_code=400)

    def test_duplicate_for_multiple_wdays_on_one_date(self):
        self.network.allow_creation_several_wdays_for_one_employee_for_one_date = True
        self.network.save()
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 14, True)
        self.create_worker_days(self.employment2, dt_from, 5, 18, 22, True)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 14, False)
        self.create_worker_days(self.employment3, dt_from, 4, 18, 22, False)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 8)
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': True,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 10)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 10)

    def test_duplicate_work_days_with_manual_work_hours(self):
        dt_now = date.today()
        WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_SICK,
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL,
        )
        WorkerDayFactory(
            employee=self.employee2,
            employment=self.employment2,
            dt=dt_now,
            type_id=WorkerDay.TYPE_SICK,
            is_approved=False,
            is_fact=False,
            work_hours=timedelta(hours=12),
        )
        data = {
            'from_employee_id': self.employee2.id,
            'from_dates': [Converter.convert_date(dt_now)],
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_now + timedelta(i)) for i in range(5)],
            'is_approved': False,
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 5)
        self.assertEqual(WorkerDay.objects.get(id=resp_data[0]['id']).work_hours, timedelta(hours=12))

    def test_duplicate_outsource_vacancy(self):
        outsource_network = Network.objects.create(
            name='outsource',
            code='outsource',
        )
        NetworkConnect.objects.create(
            client_id=self.user2.network_id,
            outsourcing=outsource_network,
        )
        outsource_shop = Shop.objects.create(
            network=outsource_network,
            name='oursource_shop',
            region=self.region,
        )
        User.objects.filter(id=self.user2.id).update(network=outsource_network)
        Employment.objects.filter(employee__user=self.user2).update(shop=outsource_shop)
        dt_from = datetime.now().date()
        self.create_worker_days(self.employment3, dt_from, 1, 9, 21, False, shop_id=self.shop2.id)
        data = {
            'from_employee_id': self.employee3.id,
            'from_dates': [Converter.convert_date(dt_from)],
            'to_employee_id': self.employee2.id,
            'to_dates':  [Converter.convert_date(dt_from)],
        }
        url = f'{self.url}duplicate/'
        resp = self.client.post(url, data, format='json')
        self.assertEqual(resp.status_code, 403)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data,
            {
                "detail": "У вас нет прав на создание типа дня \"Рабочий день\""
                          " для сотрудника Иванов И. в подразделении Shop2"
            }
        )
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.CREATE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
            employee_type=GroupWorkerDayPermission.OUTSOURCE_NETWORK_EMPLOYEE,
            shop_type=GroupWorkerDayPermission.MY_SHOPS,
        )
        resp = self.client.post(url, data, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee2, is_approved=False, shop=self.shop2,
            source=WorkerDay.SOURCE_DUPLICATE, is_vacancy=True, is_outsource=True,
        ).count(), 1)

    def test_duplicate_inner_vacancy(self):
        dt_from = datetime.now().date()
        Employment.objects.filter(employee=self.employee3).update(shop=self.shop3)
        self.create_worker_days(self.employment3, dt_from, 1, 9, 21, False, shop_id=self.shop3.id)
        data = {
            'from_employee_id': self.employee3.id,
            'from_dates': [Converter.convert_date(dt_from)],
            'to_employee_id': self.employee2.id,
            'to_dates':  [Converter.convert_date(dt_from)],
        }
        url = f'{self.url}duplicate/'
        resp = self.client.post(url, data, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(
            employee=self.employee2, is_approved=False, shop=self.shop3,
            source=WorkerDay.SOURCE_DUPLICATE, is_vacancy=True, is_outsource=False,
        ).count(), 1)
