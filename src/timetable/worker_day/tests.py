import io
import json
from copy import deepcopy
from datetime import timedelta, time, datetime, date
from unittest import skip, mock
from src.util.models_converter import Converter
import pandas
from django.db import transaction
from django.utils.timezone import now
from rest_framework.test import APITestCase

from etc.scripts.fill_calendar import main as fill_calendar
from src.base.models import WorkerPosition
from src.forecast.models import PeriodClients, OperationType, OperationTypeName
from src.timetable.models import WorkerDay, WorkType, WorkTypeName
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.test import create_departments_and_users


class TestWorkerDayStat(TestsHelperMixin, APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

        cls.dt = now().date()
        cls.worker_stat_url = '/rest_api/worker_day/worker_stat/'
        cls.url_approve = '/rest_api/worker_day/approve/'
        cls.daily_stat_url = '/rest_api/worker_day/daily_stat/'
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин')
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop,
        )
        cls.dt_const = date(2020, 12, 1)

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def create_worker_day(self, type='W', shop=None, dt=None, employee=None, employment=None, is_fact=False,
                          is_approved=False, parent_worker_day=None, is_vacancy=False, is_blocked=False, dttm_work_start=None,
                          dttm_work_end=None):
        shop = shop if shop else self.shop
        employment = employment if employment else self.employment2
        if not type == 'W':
            shop = None
        dt = dt if dt else self.dt
        employee = employee if employee else self.employee2

        return WorkerDay.objects.create(
            employee=employee,
            shop=shop,
            employment=employment,
            dt=dt,
            is_fact=is_fact,
            is_approved=is_approved,
            type=type,
            dttm_work_start=(dttm_work_start or datetime.combine(dt, time(8, 0, 0))) if type in WorkerDay.TYPES_WITH_TM_RANGE else None,
            dttm_work_end=(dttm_work_end or datetime.combine(dt, time(20, 0, 0))) if type in WorkerDay.TYPES_WITH_TM_RANGE else None,
            parent_worker_day=parent_worker_day,
            work_hours=datetime.combine(dt, time(20, 0, 0)) - datetime.combine(dt, time(8, 0, 0)),
            is_vacancy=is_vacancy,
            is_blocked=is_blocked,
        )

    def create_vacancy(self, shop=None, dt=None, is_approved=False, parent_worker_day=None):
        dt = dt if dt else self.dt
        shop = shop if shop else self.shop

        return WorkerDay.objects.create(
            shop=shop,
            dt=dt,
            is_approved=is_approved,
            type='W',
            dttm_work_start=datetime.combine(dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(dt, time(20, 0, 0)),
            parent_worker_day=parent_worker_day,
            work_hours=datetime.combine(dt, time(20, 0, 0)) - datetime.combine(dt, time(8, 0, 0)),
            is_vacancy=True,
            is_fact=False
        )

    def test_daily_stat(self):
        self.employment3.shop = self.shop2
        self.employment3.save()

        dt1 = self.dt
        dt2 = self.dt + timedelta(days=1)
        dt3 = self.dt + timedelta(days=2)
        dt4 = self.dt + timedelta(days=3)

        format = '%Y-%m-%d'

        dt1_str = dt1.strftime(format)
        dt2_str = dt2.strftime(format)
        dt3_str = dt3.strftime(format)
        dt4_str = dt4.strftime(format)
        pawd1 = self.create_worker_day(is_approved=True)
        pnawd1 = self.create_worker_day(type=WorkerDay.TYPE_HOLIDAY, parent_worker_day=pawd1)
        fawd1 = self.create_worker_day(is_approved=True, is_fact=True, parent_worker_day=pawd1)
        fnawd1 = self.create_worker_day(is_approved=False, is_fact=True, parent_worker_day=fawd1)

        pawd2 = self.create_worker_day(is_approved=True, dt=dt2, type=WorkerDay.TYPE_BUSINESS_TRIP)
        pnawd2 = self.create_worker_day(dt=dt2, type=WorkerDay.TYPE_WORKDAY, parent_worker_day=pawd2)
        # fawd2=self.create_worker_day(is_approved=True, is_fact=True, dt=dt2,parent_worker_day=pawd2)
        fnawd2 = self.create_worker_day(is_approved=False, is_fact=True, dt=dt2, parent_worker_day=pawd2)

        # Две подтвержденные вакансии. Одна na - заменяет предыдущую, вторая - новая
        vawd3 = self.create_vacancy(is_approved=True, dt=dt3)
        va2wd3 = self.create_vacancy(is_approved=True, dt=dt3)
        vnawd3 = self.create_vacancy(dt=dt3, parent_worker_day=vawd3)
        vna1wd3 = self.create_vacancy(dt=dt3)

        # print(vnawd3.__dict__)
        # print(vna1wd3.__dict__)

        pnawd3 = self.create_worker_day(
            employee=self.employee3,
            employment=self.employment3,
            is_vacancy=True,
            dt=self.dt + timedelta(days=2))
        fawd3 = self.create_worker_day(
            employee=self.employee3,
            employment=self.employment3,
            is_approved=True, is_fact=True, dt=self.dt + timedelta(days=2), parent_worker_day=pnawd3)

        pawd4 = self.create_worker_day(is_approved=True, dt=dt4)
        fnawd4 = self.create_worker_day(is_approved=False, is_fact=True, dt=dt4, parent_worker_day=pawd4)

        otn1 = OperationTypeName.objects.create(
            is_special=True,
            name='special'
        )
        ot1 = OperationType.objects.create(
            operation_type_name=otn1,
            shop=self.shop,
        )
        otn2 = OperationTypeName.objects.create(
            is_special=False,
            name='not special'
        )
        ot2 = OperationType.objects.create(
            operation_type_name=otn2,
            shop=self.shop,
            work_type=self.work_type,
        )

        for dt in [dt1]:
            for ot in [ot1, ot2]:
                for tm in range(8, 21):
                    PeriodClients.objects.create(
                        operation_type=ot,
                        value=1,
                        dttm_forecast=datetime.combine(dt, time(tm, 0, 0)),
                        type='L',
                    )

        dt_to = self.dt + timedelta(days=4)
        response = self.client.get(f"{self.daily_stat_url}?shop_id={self.shop.id}&dt_from={dt1}&dt_to={dt_to}",
                                   format='json')

        shop_empty = {'fot': 0.0, 'paid_hours': 0, 'shifts': 0}
        approved_empty = {
            'shop': shop_empty.copy(),
            'vacancies': shop_empty.copy(),
            'outsource': shop_empty.copy(),
        }

        plan_empty = {
            'approved': deepcopy(approved_empty),
            'not_approved': deepcopy(approved_empty),
            'combined': deepcopy(approved_empty),
        }
        dt_empty = {
            "plan": deepcopy(plan_empty),
            "fact": deepcopy(plan_empty),
        }

        dt1_json = deepcopy(dt_empty)
        dt1_json['plan']['approved']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt1_json['fact']['approved']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt1_json['fact']['not_approved']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt1_json['fact']['combined']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt1_json['operation_types'] = {str(ot1.id): 13.0}
        dt1_json['work_types'] = {str(ot2.work_type.id): 13.0}

        dt2_json = deepcopy(dt_empty)
        dt2_json['plan']['not_approved']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt2_json['plan']['combined']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}

        dt3_json = deepcopy(dt_empty)
        dt3_json['plan']['approved']['vacancies'] = {'shifts': 2, 'paid_hours': 21, 'fot': 0.0}
        dt3_json['plan']['not_approved']['outsource'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1612.5}
        dt3_json['plan']['not_approved']['vacancies'] = {'shifts': 2, 'paid_hours': 21, 'fot': 0.0}
        dt3_json['plan']['combined']['outsource'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1612.5}
        dt3_json['plan']['combined']['vacancies'] = {'shifts': 3, 'paid_hours': 32, 'fot': 0.0}

        dt4_json = deepcopy(dt_empty)
        dt4_json['plan']['approved']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt4_json['fact']['not_approved']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt4_json['plan']['combined']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}
        dt4_json['fact']['combined']['shop'] = {'shifts': 1, 'paid_hours': 10, 'fot': 1075.0}

        self.assertEqual(response.json()[dt1_str], dt1_json)
        self.assertEqual(response.json()[dt2_str], dt2_json)
        self.assertEqual(response.json()[dt3_str], dt3_json)
        self.assertEqual(response.json()[dt4_str], dt4_json)

    def test_approve(self):
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt + timedelta(days=4),
            'is_fact': False,
        }

        wds_not_changable = [
            self.create_worker_day(type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt - timedelta(days=1)),
            self.create_worker_day(type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt + timedelta(days=5)),
            self.create_worker_day(type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt + timedelta(days=2), is_fact=True),
            self.create_worker_day(shop=self.shop2, dt=self.dt),
            self.create_worker_day(shop=self.shop2, dt=self.dt + timedelta(days=3)),
            self.create_worker_day(type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt + timedelta(days=2), is_fact=True, is_approved=True),
        ]

        response = self.client.post(f"{self.url_approve}", data, format='json')

        self.assertEqual(response.status_code, 200)
        for wd in wds_not_changable:
            wd_from_db = WorkerDay.objects.filter(id=wd.id).first()
            self.assertIsNotNone(wd_from_db)
            self.assertEqual(wd_from_db.is_approved, wd.is_approved)
            self.assertEqual(wd_from_db.is_fact, wd.is_fact)

        wds4delete = [
            self.create_worker_day(type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt + timedelta(days=1), is_approved=True),
            self.create_worker_day(type=WorkerDay.TYPE_VACATION, shop=self.shop, dt=self.dt + timedelta(days=2), is_approved=True),
            self.create_worker_day(type=WorkerDay.TYPE_SICK, shop=self.shop, dt=self.dt + timedelta(days=4), is_approved=True),
        ]

        wds4updating = [
            self.create_worker_day(type=WorkerDay.TYPE_SICK, shop=self.shop, dt=self.dt + timedelta(days=1)),
            self.create_worker_day(type=WorkerDay.TYPE_SICK, shop=self.shop, dt=self.dt + timedelta(days=2)),
            self.create_worker_day(type=WorkerDay.TYPE_VACATION, shop=self.shop, dt=self.dt + timedelta(days=4)),
        ]

        response = self.client.post(f"{self.url_approve}", data, format='json')
        self.assertEqual(response.status_code, 200)
        for wd in wds_not_changable:
            wd_from_db = WorkerDay.objects.filter(id=wd.id).first()
            self.assertIsNotNone(wd_from_db)
            self.assertEqual(wd_from_db.is_approved, wd.is_approved)
            self.assertEqual(wd_from_db.is_fact, wd.is_fact)

        for wd in wds4delete:
            wd_from_db = WorkerDay.objects.filter(id=wd.id).first()
            self.assertIsNone(wd_from_db)

        for wd in wds4updating:
            wd_from_db = WorkerDay.objects.filter(id=wd.id).first()
            wd_from_db_not_approved = WorkerDay.objects.filter(dt=wd.dt, employee_id=wd.employee_id, is_approved=False).first()
            self.assertEqual(wd_from_db.is_approved, True)
            self.assertIsNotNone(wd_from_db_not_approved)
            self.assertEqual(wd_from_db.work_hours, wd_from_db_not_approved.work_hours)

    def test_cant_approve_protected_day_without_perm(self):
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt,
            'is_fact': False,
        }

        self.create_worker_day(shop=self.shop2, dt=self.dt, is_blocked=True, is_approved=True)
        self.create_worker_day(shop=self.shop2, dt=self.dt, type=WorkerDay.TYPE_HOLIDAY)

        response = self.client.post(f"{self.url_approve}", data, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()['detail'],
            f'У вас нет прав на подтверждение защищенных рабочих дней '
            f'({self.user2.last_name} {self.user2.first_name} ({self.user2.username}): {self.dt.strftime("%Y-%m-%d")}). '
            'Обратитесь, пожалуйста, к администратору системы.'
        )

    def test_can_approve_protected_day_with_perm(self):
        self.admin_group.has_perm_to_change_protected_wdays = True
        self.admin_group.save()

        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt,
            'is_fact': False,
        }

        protected_day = self.create_worker_day(shop=self.shop2, dt=self.dt, is_blocked=True, is_approved=True)
        day_to_approve = self.create_worker_day(shop=self.shop2, dt=self.dt, type=WorkerDay.TYPE_HOLIDAY)

        response = self.client.post(f"{self.url_approve}", data, format='json')

        self.assertEqual(response.status_code, 200)

        self.assertFalse(WorkerDay.objects.filter(id=protected_day.id).exists())
        self.assertTrue(WorkerDay.objects.get(id=day_to_approve.id).is_approved)

    def test_send_doctors_schedule_on_approve(self):
        with self.settings(SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE=True, CELERY_TASK_ALWAYS_EAGER=True):
            # другой тип работ -- не отправляется
            WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt - timedelta(days=3), is_approved=False,
                cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                cashbox_details__work_type__work_type_name__code='consult',
            )
            WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt - timedelta(days=3), is_approved=True,
            )

            # создание рабочего дня (без дня в подтв. версии) -- отправляется
            wd_create1 = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt - timedelta(days=2), is_approved=False,
                cashbox_details__work_type__work_type_name__name='Врач',
                cashbox_details__work_type__work_type_name__code='doctor',
            )

            # создание рабочего дня (с днем в подтв. версии) -- отправляется
            wd_create2 = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt - timedelta(days=1), is_approved=False,
                cashbox_details__work_type__work_type_name__name='Врач',
                cashbox_details__work_type__work_type_name__code='doctor',
            )
            WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt - timedelta(days=1), is_approved=True,
            )

            # обновление рабочего дня -- отправляется
            wd_update = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt, is_approved=False,
                dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
                dttm_work_end=datetime.combine(self.dt, time(21, 0, 0)),
                cashbox_details__work_type__work_type_name__name='Врач',
                cashbox_details__work_type__work_type_name__code='doctor',
            )
            WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt, is_approved=True,
                dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
                dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
                cashbox_details__work_type__work_type_name__name='Врач',
                cashbox_details__work_type__work_type_name__code='doctor',
            )

            # удаление рабочего дня -- отправляется
            WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt + timedelta(days=1), is_approved=False,
            )
            wd_delete1 = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt + timedelta(days=1), is_approved=True,
                dttm_work_start=datetime.combine(self.dt, time(11, 0, 0)),
                dttm_work_end=datetime.combine(self.dt, time(21, 0, 0)),
                cashbox_details__work_type__work_type_name__name='Врач',
                cashbox_details__work_type__work_type_name__code='doctor',
            )

            # не рабочие дни -- не отправляется
            WorkerDayFactory(
                employee=self.employee2,
                type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=self.dt + timedelta(days=2), is_approved=False,
            )
            WorkerDayFactory(
                employee=self.employee2,
                type=WorkerDay.TYPE_VACATION, shop=self.shop, dt=self.dt + timedelta(days=2), is_approved=True,
            )

            # разные work_type, тип врач в неподтв. версии -- отправляется создание
            wd_create3 = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt + timedelta(days=3), is_approved=False,
                dttm_work_start=datetime.combine(self.dt + timedelta(days=3), time(8, 0, 0)),
                dttm_work_end=datetime.combine(self.dt + timedelta(days=3), time(21, 0, 0)),
                cashbox_details__work_type__work_type_name__name='Врач',
                cashbox_details__work_type__work_type_name__code='doctor',
            )
            WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt + timedelta(days=3), is_approved=True,
                dttm_work_start=datetime.combine(self.dt + timedelta(days=3), time(8, 0, 0)),
                dttm_work_end=datetime.combine(self.dt + timedelta(days=3), time(20, 0, 0)),
                cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                cashbox_details__work_type__work_type_name__code='consult',
            )

            # разные work_type, тип врач в подтв. версии -- отправляется удаление
            WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt + timedelta(days=4), is_approved=False,
                dttm_work_start=datetime.combine(self.dt + timedelta(days=4), time(8, 0, 0)),
                dttm_work_end=datetime.combine(self.dt + timedelta(days=4), time(21, 0, 0)),
                cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                cashbox_details__work_type__work_type_name__code='consult',
            )
            wd_delete2 = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=self.dt + timedelta(days=4), is_approved=True,
                dttm_work_start=datetime.combine(self.dt + timedelta(days=4), time(8, 0, 0)),
                dttm_work_end=datetime.combine(self.dt + timedelta(days=4), time(20, 0, 0)),
                cashbox_details__work_type__work_type_name__name='Врач',
                cashbox_details__work_type__work_type_name__code='doctor',
            )

            data = {
                'shop_id': self.shop.id,
                'dt_from': self.dt - timedelta(days=2),
                'dt_to': self.dt + timedelta(days=4),
                'is_fact': False,
            }
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                from src.celery.tasks import send_doctors_schedule_to_mis
                with mock.patch.object(send_doctors_schedule_to_mis, 'delay') as send_doctors_schedule_to_mis_delay:
                    response = self.client.post(f"{self.url_approve}", data, format='json')
                    self.assertEqual(response.status_code, 200)
                    send_doctors_schedule_to_mis_delay.assert_called_once()
                    json_data = json.loads(send_doctors_schedule_to_mis_delay.call_args[1]['json_data'])
                    self.assertListEqual(
                        sorted(json_data, key=lambda i: (i['dt'], i['employee__user__username'])),
                        sorted([
                            {
                                "dt": Converter.convert_date(wd_create1.dt),
                                "employee__user__username": self.user2.username,
                                "shop__code": self.shop.code,
                                "dttm_work_start": Converter.convert_datetime(wd_create1.dttm_work_start),
                                "dttm_work_end": Converter.convert_datetime(wd_create1.dttm_work_end),
                                "action": "create"
                            },
                            {
                                "dt": Converter.convert_date(wd_create2.dt),
                                "employee__user__username": self.user2.username,
                                "shop__code": self.shop.code,
                                "dttm_work_start": Converter.convert_datetime(wd_create2.dttm_work_start),
                                "dttm_work_end": Converter.convert_datetime(wd_create2.dttm_work_end),
                                "action": "create"
                            },
                            {
                                "dt": Converter.convert_date(wd_update.dt),
                                "employee__user__username": self.user2.username,
                                "shop__code": self.shop.code,
                                "dttm_work_start": Converter.convert_datetime(wd_update.dttm_work_start),
                                "dttm_work_end": Converter.convert_datetime(wd_update.dttm_work_end),
                                "action": "update"
                            },
                            {
                                "dt": Converter.convert_date(wd_create3.dt),
                                "employee__user__username": self.user2.username,
                                "shop__code": self.shop.code,
                                "dttm_work_start": Converter.convert_datetime(wd_create3.dttm_work_start),
                                "dttm_work_end": Converter.convert_datetime(wd_create3.dttm_work_end),
                                "action": "create"
                            },
                            {
                                "dt": Converter.convert_date(wd_delete2.dt),
                                "employee__user__username": self.user2.username,
                                "shop__code": self.shop.code,
                                "dttm_work_start": Converter.convert_datetime(wd_delete2.dttm_work_start),
                                "dttm_work_end": Converter.convert_datetime(wd_delete2.dttm_work_end),
                                "action": "delete"
                            },
                            {
                                "dt": Converter.convert_date(wd_delete1.dt),
                                "employee__user__username": self.user2.username,
                                "shop__code": self.shop.code,
                                "dttm_work_start": Converter.convert_datetime(wd_delete1.dttm_work_start),
                                "dttm_work_end": Converter.convert_datetime(wd_delete1.dttm_work_end),
                                "action": "delete"
                            },
                        ], key=lambda i: (i['dt'], i['employee__user__username']))
                    )


class TestUploadDownload(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        create_departments_and_users(self)
        WorkerPosition.objects.bulk_create(
            [
                WorkerPosition(
                    name=name,
                )
                for name in ['Директор магазина', 'Продавец', 'Продавец-кассир', 'ЗДМ']
            ]
        )

        WorkType.objects.create(work_type_name=WorkTypeName.objects.create(name='Кассы'), shop_id=self.shop.id)
        self.url = '/rest_api/worker_day/'
        self.client.force_authenticate(user=self.user1)

    def test_upload_timetable(self):
        file = open('etc/scripts/timetable.xlsx', 'rb')
        response = self.client.post(f'{self.url}upload/', {'shop_id': self.shop.id, 'file': file})
        file.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 150)

    @skip('Сервер не доступен')
    def test_download_tabel(self):
        fill_calendar('2020.4.1', '2021.12.31', self.region.id)
        with open('etc/scripts/timetable.xlsx', 'rb') as f:
            self.client.post(f'{self.url}upload/', {'shop_id': self.shop.id, 'file': f})
        response = self.client.get(
            f'{self.url}download_tabel/?shop_id={self.shop.id}&dt_from=2020-04-01&is_approved=False&dt_to=2020-04-30')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tabel[tabel.columns[1]][1], 'ТАБЕЛЬ УЧЕТА РАБОЧЕГО ВРЕМЕНИ АПРЕЛЬ  2020г.')
        self.assertEqual(tabel[tabel.columns[7]][20], '10')

    def test_download_timetable(self):
        fill_calendar('2020.4.1', '2021.12.31', self.region.id)
        file = open('etc/scripts/timetable.xlsx', 'rb')
        self.client.post(f'{self.url}upload/', {'shop_id': self.shop.id, 'file': file})
        file.close()
        response = self.client.get(
            f'{self.url}download_timetable/?shop_id={self.shop.id}&dt_from=2020-04-01&is_approved=False')
        tabel = pandas.read_excel(io.BytesIO(response.content))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tabel[tabel.columns[1]][0], 'Магазин: Shop1') #fails with python > 3.6
        self.assertEqual(tabel[tabel.columns[1]][12], 'Иванов Иван Иванович')
        self.assertEqual(tabel[tabel.columns[27]][15], 'В')
