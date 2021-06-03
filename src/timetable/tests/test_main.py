import json
import uuid
from datetime import timedelta, time, datetime, date
from unittest import mock

from dateutil.relativedelta import relativedelta
from django.core import mail
from django.db import transaction
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import FunctionGroup, Network, Employment, ShopSchedule, Shop, Employee
from src.events.models import EventType
from src.notifications.models.event_notification import EventEmailNotification
from src.timetable.events import VACANCY_CONFIRMED_TYPE
from src.timetable.models import (
    WorkerDay,
    AttendanceRecords,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayPermission,
    GroupWorkerDayPermission,
    EmploymentWorkType,
)
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter
from src.util.test import create_departments_and_users


class TestWorkerDay(TestsHelperMixin, APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    maxDiff = None

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = (now() + timedelta(hours=3)).date()

        create_departments_and_users(self)
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)
        self.work_type2 = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop2)

        self.worker_day_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            is_approved=True,
        )
        self.worker_day_plan_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            parent_worker_day=self.worker_day_plan_approved
        )
        self.worker_day_fact_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 30, 0)),
            is_approved=True,
            parent_worker_day=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 59, 1)),
            parent_worker_day=self.worker_day_fact_approved
        )

        self.client.force_authenticate(user=self.user1)
        self.network.allowed_interval_for_late_arrival = timedelta(minutes=15)
        self.network.allowed_interval_for_early_departure = timedelta(minutes=15)
        self.network.crop_work_hours_by_shop_schedule = False
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()

        self.shop.tm_open_dict = f'{{"all":"00:00:00"}}'
        self.shop.tm_close_dict = f'{{"all":"00:00:00"}}'
        self.shop.save()

    def test_get_list(self):
        dt = Converter.convert_date(self.dt)

        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&dt={dt}')
        self.assertEqual(len(response.json()), 4)

        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_fact=1&dt={dt}')
        self.assertEqual(len(response.json()), 2)

        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_fact=0&dt={dt}')
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.worker_day_plan_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.worker_day_plan_not_approved.id,
            'shop_id': self.shop.id,
            'employee_id': self.employee2.id,
            'employment_id': self.employment2.id,
            'is_fact': False,
            'is_approved': False,
            'is_blocked': False,
            'type': WorkerDay.TYPE_WORKDAY,
            'parent_worker_day_id': self.worker_day_plan_approved.id,
            'comment': None,
            'dt': Converter.convert_date(self.dt),
            'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_start_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'dttm_work_end_tabel': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'work_hours': '10:45:00',
            'worker_day_details': [],
            'is_outsource': False,
            'outsources': [],
            'is_vacancy': False,
            'crop_work_hours_by_shop_schedule': True,
        }

        self.assertEqual(response.json(), data)

    def test_approve(self):
        # Approve plan
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt + timedelta(days=2),
            'is_fact': False,
            # 'wd_types': WorkerDay.TYPES_USED,  # временно
        }
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # не должен подтвердиться, т.к. нету изменений в дне
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).is_approved, False)

        WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).update(
            dttm_work_start=datetime.combine(self.dt, time(8, 30, 0))
        )
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).is_approved, True)

        # self.assertIsNone(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).parent_worker_day_id)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())
        # self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).parent_worker_day_id,
        #                  self.worker_day_plan_not_approved.id)

        # Approve fact
        data['is_fact'] = True

        # plan(approved) <- fact0(approved) <- fact1(not approved) ==> plan(approved) <- fact1(approved)
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())
        # self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id,
        #                  self.worker_day_plan_not_approved.id)

    # Последовательное создание и подтверждение P1 -> A1 -> P2 -> F1 -> A2 -> F2
    def test_create_and_approve(self):
        GroupWorkerDayPermission.objects.filter(
            group=self.admin_group,
            worker_day_permission__action=WorkerDayPermission.APPROVE,
        ).delete()
        dt = self.dt + timedelta(days=1)

        data_holiday = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_HOLIDAY,
        }

        # create not approved plan
        response = self.client.post(self.url, data_holiday, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 0)

        # edit not approved plan
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], plan_id)
        self.assertEqual(response.json()['type'], data['type'])
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 1)

        # Approve plan
        approve_dt_from = dt - timedelta(days=5)
        approve_dt_to = dt + timedelta(days=2)
        data_approve = {
            'shop_id': self.shop.id,
            'dt_from': approve_dt_from,
            'dt_to': approve_dt_to,
            'is_fact': False,
            'wd_types': WorkerDay.TYPES_USED,
        }

        response = self.client.post(self.url_approve, data_approve, format='json')
        # если нету ни одного разрешения для action=approve, то ответ -- 403
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        gwdp = GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type=WorkerDay.TYPE_HOLIDAY,
            ),
            limit_days_in_past=3,
            limit_days_in_future=1,
        )
        response = self.client.post(self.url_approve, data_approve, format='json')
        # разрешено изменять день только на 1 день в будущем
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertDictEqual(
            response.json(),
            {
                'detail': 'У вас нет прав на подтверждения типа дня "Выходной" в выбранные '
                          'даты. Необходимо изменить интервал для подтверждения. '
                          'Разрешенный интевал для подтверждения: '
                          f'с {Converter.convert_date(self.dt - timedelta(days=gwdp.limit_days_in_past))} '
                          f'по {Converter.convert_date(self.dt + timedelta(days=gwdp.limit_days_in_future))}'
            }
        )

        gwdp.limit_days_in_past = 10
        gwdp.limit_days_in_future = 5
        gwdp.save()

        response = self.client.post(self.url_approve, data_approve, format='json')
        # проверка наличия прав на редактирование переданных типов дней
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertDictEqual(
            response.json(),
            {
                'detail': 'У вас нет прав на подтверждение типа дня "Рабочий день"'
            }
        )

        for wdp in WorkerDayPermission.objects.filter(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.PLAN):
            GroupWorkerDayPermission.objects.get_or_create(
                group=self.admin_group,
                worker_day_permission=wdp,
            )

        data_approve['wd_types'] = [WorkerDay.TYPE_HOLIDAY]
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # день не должен подтвердиться, т.к. передан тип только выходной, а у нас рабочий день
        self.assertEqual(WorkerDay.objects.get(id=plan_id).is_approved, False)

        data_approve['wd_types'] = WorkerDay.TYPES_USED
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).is_approved, True)

        # create not approved fact
        data['is_fact'] = True
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']

        # edit not approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(7, 48, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(20, 2, 0)))

        response = self.client.put(f"{self.url}{fact_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], fact_id)
        self.assertEqual(response.json()['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(response.json()['dttm_work_end'], data['dttm_work_end'])

        # Approve plan again to check fact is not approved
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=fact_id).is_approved, False)

        # Approve fact
        data_approve['is_fact'] = True

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.is_approved, False)

        for wdp in WorkerDayPermission.objects.filter(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.FACT):
            GroupWorkerDayPermission.objects.get_or_create(
                group=self.admin_group,
                worker_day_permission=wdp,
            )

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=fact_id).is_approved, True)

        # create approved plan
        data['is_fact'] = False
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_plan_id = response.json()['id']
        new_plan = WorkerDay.objects.get(id=new_plan_id)
        self.assertNotEqual(new_plan_id, plan_id)
        self.assertEqual(response.json()['type'], data['type'])

        # # create approved plan again
        # response = self.client.post(f"{self.url}", data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

        # edit approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(8, 8, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(21, 2, 0)))

        data['is_fact'] = True
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        res = response.json()
        new_fact_id = res['id']
        new_fact = WorkerDay.objects.get(id=new_fact_id)
        self.assertNotEqual(new_fact_id, fact_id)
        self.assertEqual(res['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(res['dttm_work_end'], data['dttm_work_end'])

        # # create approved fact again
        # response = self.client.post(f"{self.url}", data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

    def test_approve_fact_when_approved_and_not_approved_version_differs_only_by_end_time(self):
        WorkerDay.objects.filter(
            id=self.worker_day_fact_approved.id,
        ).update(
            dttm_work_start=datetime.combine(self.worker_day_fact_approved.dt, time(10)),
            dttm_work_end=None,
        )
        WorkerDay.objects.filter(
            id=self.worker_day_fact_not_approved.id,
        ).update(
            dttm_work_start=datetime.combine(self.worker_day_fact_not_approved.dt, time(10)),
            dttm_work_end=datetime.combine(self.worker_day_fact_not_approved.dt, time(19)),
        )

        data_approve = {
            'shop_id': self.shop.id,
            'dt_from': self.worker_day_fact_approved.dt,
            'dt_to': self.worker_day_fact_approved.dt,
            'is_fact': True,
            'wd_types': WorkerDay.TYPES_USED,
        }

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).exists())

    def test_empty_params(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": []
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_not_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'worker_day_details': ['Это поле обязательно.']})

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_BUSINESS_TRIP,
            # "dttm_work_start": None,
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}]
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_not_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'dttm_work_start': ['Это поле обязательно.']})

    def test_edit_approved_wd_secondly(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": 1}
            ]
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(),
                         {'error': ['Нельзя менять подтвержденную версию.']}
                         )

        response = self.client.put(f"{self.url}{self.worker_day_fact_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': ['Нельзя менять подтвержденную версию.']})

    def test_edit_worker_day(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved plan
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 1)
        data["worker_day_details"] = [{
            "work_part": 0.5,
            "work_type_id": self.work_type.id},
            {
                "work_part": 0.5,
                "work_type_id": self.work_type.id}]
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 2)

    def test_edit_worker_day_with_shop_code_and_username(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_code": self.shop.code,
            "username": self.user2.username,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved plan
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 1)
        data["worker_day_details"] = [{
            "work_part": 0.5,
            "work_type_id": self.work_type.id},
            {
                "work_part": 0.5,
                "work_type_id": self.work_type.id}]
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day_id=plan_id).count(), 2)


    def test_edit_worker_day_last_edited_by(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "username": self.user2.username,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved plan
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=plan_id).created_by_id, self.user1.id)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).last_edited_by_id, self.user1.id)
        data["worker_day_details"] = [{
            "work_part": 0.5,
            "work_type_id": self.work_type.id},
            {
                "work_part": 0.5,
                "work_type_id": self.work_type.id}]
        self.client.force_authenticate(user=self.user2)
        self.employment2.function_group = self.admin_group
        self.employment2.save()
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).created_by_id, self.user1.id)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).last_edited_by_id, self.user2.id)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&dt={dt}')
        self.assertEqual(
            response.json()[0]['last_edited_by'],
            {
                'id': self.user2.id,
                'first_name': self.user2.first_name,
                'last_name': self.user2.last_name,
                'middle_name': None,
                'avatar': None,
            }
        )


    def test_delete(self):
        # План подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': 'Нельзя удалить подтвержденную версию.'})

        # План неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())

        # Факт подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': 'Нельзя удалить подтвержденную версию.'})

        # Факт неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_not_approved.id).exists())

    def test_S_type_plan_approved_returned_in_tabel_if_fact_approved_is_missing(self):
        WorkerDay.objects.filter(
            id=self.worker_day_plan_approved.id,
        ).update(type=WorkerDay.TYPE_SICK)
        WorkerDay.objects.filter(
            id=self.worker_day_fact_approved.id,  # не удаляется, поэтому обновим дату на другой день
        ).update(parent_worker_day=None, dt=self.dt - timedelta(days=365))

        get_params = {
            'shop_id': self.shop.id,
            'limit': 100,
            'fact_tabel': 'true',
            'dt__gte': (self.dt - timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt__lte': self.dt.strftime('%Y-%m-%d'),
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], 'S')

    def _test_tabel(self, plan_start, plan_end, fact_start, fact_end, expected_start, expected_end, expected_hours,
                    extra_get_params=None, tabel_kwarg='fact_tabel'):
        self.worker_day_plan_approved.shop.network.refresh_from_db()
        self.worker_day_fact_approved.shop.network.refresh_from_db()

        plan_dttm_work_start = plan_start
        plan_dttm_work_end = plan_end
        self.worker_day_plan_approved.dttm_work_start = plan_dttm_work_start
        self.worker_day_plan_approved.dttm_work_end = plan_dttm_work_end
        self.worker_day_plan_approved.save()

        fact_dttm_work_start = fact_start
        fact_dttm_work_end = fact_end
        self.worker_day_fact_approved.dttm_work_start = fact_dttm_work_start
        self.worker_day_fact_approved.dttm_work_end = fact_dttm_work_end
        self.worker_day_fact_approved.save()
        get_params = {'shop_id': self.shop.id, 'limit': 100,
                      'dt__gte': (self.dt - timedelta(days=5)),
                      'dt__lte': self.dt, tabel_kwarg: 'true'}
        get_params.update(extra_get_params or {})
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], 'W')
        self.assertEqual(resp_data[0]['dttm_work_start_tabel'], Converter.convert_datetime(expected_start))
        self.assertEqual(resp_data[0]['dttm_work_end_tabel'], Converter.convert_datetime(expected_end))
        self.assertEqual(resp_data[0]['work_hours'], expected_hours)
        return resp_data

    def test_tabel_early_arrival_and_late_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(12, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(11, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=7.0,
        )

    def test_tabel_late_arrival_and_late_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(9, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(11, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=8.0,
        )

    def test_tabel_early_arrival_and_early_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(11, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=8.0,
        )

    def test_tabel_allowed_late_arrival(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(22, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(10, 7, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 0, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=8.75,
        )

    def test_tabel_allowed_early_departure(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(21, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(9, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 53, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=9.75,
        )

    def test_can_override_tabel_settings(self):
        Network.objects.filter(id=self.network.id).update(
            allowed_interval_for_late_arrival=timedelta(seconds=0),
            allowed_interval_for_early_departure=timedelta(seconds=0),
        )
        self.network.refresh_from_db()

        plan_dttm_work_start = datetime.combine(self.dt, time(10, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(21, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(9, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(20, 53, 0))

        self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=plan_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=9.63,
        )

    def test_get_hours_details_for_tabel(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(16, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(16, 40, 0))
        fact_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 20, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=plan_dttm_work_end,
            expected_hours=9.09,
            extra_get_params=dict(
                hours_details=True,
            )
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 4.71, 'N': 4.38}, resp_data[0]['work_hours_details'])

    def test_fill_empty_days_param_only_plan_exists_returns_zero_hours_workday(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).delete()
        get_params = {
            'employment__tabel_code__in': self.employee2.tabel_code,
            'dt__gte': self.dt,
            'dt__lte': self.dt,
            'fact_tabel': 'true',
            'fill_empty_days': 'true',
            'hours_details': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['id'], None)
        self.assertEqual(resp_data[0]['type'], WorkerDay.TYPE_WORKDAY)
        self.assertEqual(resp_data[0]['work_hours'], 0)
        self.assertEqual(resp_data[0]['work_hours_details']['D'], 0)

    def test_fill_empty_days_param_only_plan_exists_returns_absense_in_past(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).delete()
        WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).update(
            dt=self.dt - timedelta(days=1),
            dttm_work_start=self.worker_day_plan_approved.dttm_work_start - timedelta(days=1),
            dttm_work_end=self.worker_day_plan_approved.dttm_work_end - timedelta(days=1),
        )
        get_params = {
            'employment__tabel_code__in': self.employee2.tabel_code,
            'dt__gte': self.dt - timedelta(days=1),
            'dt__lte': self.dt - timedelta(days=1),
            'fact_tabel': 'true',
            'fill_empty_days': 'true',
            'hours_details': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['id'], None)
        self.assertEqual(resp_data[0]['type'], WorkerDay.TYPE_ABSENSE)

    def test_fill_empty_days_param_no_days_exists_returns_holiday(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).delete()
        WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).delete()
        get_params = {
            'employment__tabel_code__in': self.employee2.tabel_code,
            'dt__gte': self.dt,
            'dt__lte': self.dt,
            'fact_tabel': 'true',
            'fill_empty_days': 'true',
            'hours_details': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], WorkerDay.TYPE_HOLIDAY)

    def test_work_hours_as_decimal_for_plan_approved(self):
        get_params = {'shop_id': self.shop.id,
                      'dt__gte': self.worker_day_plan_approved.dt,
                      'dt__lte': self.worker_day_plan_approved.dt,
                      'is_fact': False, 'is_approved': True}
        resp = self.client.get('/rest_api/worker_day/', data=get_params)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['work_hours'], 10.75)

    def test_get_hours_details_for_plan_approved(self):
        get_params = {'shop_id': self.shop.id,
                      'dt__gte': self.worker_day_plan_approved.dt,
                      'dt__lte': self.worker_day_plan_approved.dt,
                      'is_fact': False, 'is_approved': True, 'hours_details': True}
        resp = self.client.get('/rest_api/worker_day/', data=get_params)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['work_hours'], 10.75)
        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 10.75, 'N': 0.0}, resp_data[0]['work_hours_details'])

    def test_get_fact_tabel(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(12, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(17, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(3, 0, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=8.76,
            extra_get_params=dict(
                hours_details=True,
            ),
            tabel_kwarg='fact_tabel',
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 4.38, 'N': 4.38}, resp_data[0]['work_hours_details'])

    def test_get_fact_tabel2(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(12, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt, time(23, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(18, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt, time(23, 0, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=4.5,
            extra_get_params=dict(
                hours_details=True,
            ),
            tabel_kwarg='fact_tabel',
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 3.75, 'N': 0.75}, resp_data[0]['work_hours_details'])

    def test_get_fact_tabel3(self):
        plan_dttm_work_start = datetime.combine(self.dt, time(18, 0, 0))
        plan_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(9, 0, 0))
        fact_dttm_work_start = datetime.combine(self.dt, time(18, 0, 0))
        fact_dttm_work_end = datetime.combine(self.dt + timedelta(days=1), time(9, 0, 0))

        resp_data = self._test_tabel(
            plan_start=plan_dttm_work_start,
            plan_end=plan_dttm_work_end,
            fact_start=fact_dttm_work_start,
            fact_end=fact_dttm_work_end,
            expected_start=fact_dttm_work_start,
            expected_end=fact_dttm_work_end,
            expected_hours=13.76,
            extra_get_params=dict(
                hours_details=True,
            ),
            tabel_kwarg='fact_tabel',
        )

        self.assertIn('work_hours_details', resp_data[0])
        self.assertDictEqual({'D': 6.38, 'N': 7.38}, resp_data[0]['work_hours_details'])

    def test_get_worker_day_by_worker__username__in(self):
        get_params = {
            'worker__username__in': self.user2.username,
            'is_fact': 'true',
            'is_approved': 'true',
            'dt__gte': (self.dt - timedelta(days=5)),
            'dt__lte': self.dt,
            'by_code': 'true',
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)

    def test_can_create_and_update_not_approved_fact_only_with_empty_or_workday_type(self):
        dt = now().date()
        data = {
            "shop_code": self.shop.code,
            "username": self.user2.username,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_HOLIDAY,
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ],
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, 400)

        data['type'] = WorkerDay.TYPE_EMPTY
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        wd_id = response.json()['id']
        self.assertEqual(WorkerDay.objects.filter(id=wd_id).count(), 1)

        data['type'] = WorkerDay.TYPE_WORKDAY
        data['dttm_work_start'] = datetime.combine(dt, time(8, 0, 0))
        data['dttm_work_end'] = datetime.combine(dt, time(20, 0, 0))

        # create plan
        data['is_fact'] = False
        response = self.client.put(f"{self.url}{wd_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # approve plan
        data_approve = {
            'shop_id': self.shop.id,
            'dt_from': dt,
            'dt_to': dt,
            'is_fact': False,
        }
        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # create fact
        data['is_fact'] = True
        response = self.client.put(f"{self.url}{wd_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def _test_wd_perm(self, url, method, action, graph_type=None, wd_type=None):
        assert method == 'delete' or (graph_type and wd_type)
        GroupWorkerDayPermission.objects.all().delete()

        dt = self.dt + timedelta(days=1)
        if method == 'delete':
            data = None
        else:
            data = {
                "shop_id": self.shop.id,
                "employee_id": self.employee2.id,
                "employment_id": self.employment2.id,
                "dt": dt,
                "is_fact": True if graph_type == WorkerDayPermission.FACT else False,
                "type": wd_type,
            }
            if wd_type == WorkerDay.TYPE_WORKDAY:
                data.update({
                    "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
                    "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
                    "worker_day_details": [{
                        "work_part": 1.0,
                        "work_type_id": self.work_type.id}
                    ]
                })

        response = getattr(self.client, method)(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=action,
                graph_type=graph_type,
                wd_type=wd_type,
            )
        )
        response = getattr(self.client, method)(url, data, format='json')
        method_to_status_mapping = {
            'post': status.HTTP_201_CREATED,
            'put': status.HTTP_200_OK,
            'delete': status.HTTP_204_NO_CONTENT,
        }
        self.assertEqual(response.status_code, method_to_status_mapping.get(method))

    def test_worker_day_permissions(self):
        # create
        self._test_wd_perm(
            self.url, 'post', WorkerDayPermission.CREATE_OR_UPDATE, WorkerDayPermission.PLAN, WorkerDay.TYPE_WORKDAY)
        wd = WorkerDay.objects.last()

        # update
        self._test_wd_perm(
            f"{self.url}{wd.id}/", 'put',
            WorkerDayPermission.CREATE_OR_UPDATE, WorkerDayPermission.PLAN, WorkerDay.TYPE_HOLIDAY,
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type, WorkerDay.TYPE_HOLIDAY)

        # delete
        self._test_wd_perm(
            f"{self.url}{wd.id}/", 'delete',
            WorkerDayPermission.DELETE,
            WorkerDayPermission.PLAN,
            wd.type,
        )

    def test_cant_create_worker_day_with_shop_mismatch(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type2.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['worker_day_details'][0], 'Магазин в типе работ и в рабочем дне должен совпадать.')

    def test_cant_create_worker_day_with_worker_mismatch(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment3.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['employment'][0], 'Сотрудник в трудоустройстве и в рабочем дне должны совпадать.')

    def test_change_range(self):
        self.employee2.tabel_code = 'empl_2'
        self.employee2.save()

        data = {
          "ranges": [
            {
              "worker": self.employee2.tabel_code,
              "dt_from": self.dt - timedelta(days=10),
              "dt_to": self.dt + timedelta(days=10),
              "type": WorkerDay.TYPE_MATERNITY,
              "is_fact": False,
              "is_approved": True
            }
          ]
        }
        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.employee2.tabel_code: {'created_count': 21, 'deleted_count': 1, 'existing_count': 0}}
        )
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())
        self.assertEqual(
            WorkerDay.objects.filter(employee__tabel_code=self.employee2.tabel_code, type=WorkerDay.TYPE_MATERNITY).count(),
            21,
        )

        response = self.client.post(reverse('WorkerDay-change-range'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {self.employee2.tabel_code: {'created_count': 0, 'deleted_count': 0, 'existing_count': 21}}
        )

        wd = WorkerDay.objects.filter(
            employee=self.employee2,
            dt=self.dt,
            is_fact=False,
            is_approved=True,
            type=WorkerDay.TYPE_MATERNITY,
        ).last()
        self.assertIsNotNone(wd.created_by)
        self.assertEqual(wd.created_by.id, self.user1.id)

    def test_cant_create_workday_if_user_has_no_active_employment(self):
        WorkerDay.objects_with_excluded.filter(employee=self.employee2).delete()
        Employment.objects.filter(employee__user=self.user2).delete()
        dt = self.dt - timedelta(days=60)
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": dt,
            "is_fact": False,
            "is_approved": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.json()[0],
            'Невозможно создать рабочий день, так как пользователь в этот период не трудоустроен',
        )

    def test_wd_created_as_vacancy_for_other_shop_and_employment_was_set(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee8.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        wd = WorkerDay.objects.get(id=resp_data['id'])
        self.assertTrue(wd.is_vacancy)
        self.assertEqual(wd.employment.id, self.employment8.id)

    def test_create_vacancy_for_the_same_shop_then_update_for_other_shop(self):
        data = {
            "shop_id": self.shop2.id,
            "employee_id": self.employee8.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type2.id}
            ]
        }
        resp = self.client.post(self.get_url('WorkerDay-list'), data, format='json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        wd = WorkerDay.objects.get(id=resp_data['id'])
        self.assertFalse(wd.is_vacancy)
        self.assertEqual(wd.employment.id, self.employment8.id)

        data['shop_id'] = self.shop.id
        data['worker_day_details'][0]['work_type_id'] = self.work_type.id
        resp = self.client.put(self.get_url('WorkerDay-detail', pk=wd.pk), data, format='json')
        self.assertEqual(resp.status_code, 200)
        wd.refresh_from_db()
        self.assertTrue(wd.is_vacancy)

        data['shop_id'] = self.shop2.id
        data['worker_day_details'][0]['work_type_id'] = self.work_type2.id
        resp = self.client.put(self.get_url('WorkerDay-detail', pk=wd.pk), data, format='json')
        self.assertEqual(resp.status_code, 200)
        wd.refresh_from_db()
        self.assertFalse(wd.is_vacancy)

    def test_inactive_employment_replaced_by_active(self):
        Employment.objects.filter(id=self.employment2.id).update(
            dt_hired=self.dt - timedelta(days=100),
            dt_fired=self.dt - timedelta(days=1),
        )
        e2_2 = Employment.objects.create(
            code=f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            employee=self.employee2,
            shop=self.shop2,
            function_group=self.employee_group,
            dt_hired=self.dt,
            dt_fired=self.dt + timedelta(days=100),
        )
        data = {
            "shop_id": self.shop2.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type2.id}
            ]
        }
        resp = self.client.post(self.get_url('WorkerDay-list'), data, format='json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        wd = WorkerDay.objects.get(id=resp_data['id'])
        self.assertEqual(wd.employment.id, e2_2.id)

    # def test_cant_create_fact_worker_day_when_there_is_no_plan(self):
    #     data = {
    #         "shop_id": self.shop2.id,
    #         "worker_id": self.user8.id,
    #         "dt": self.dt,
    #         "is_fact": True,
    #         "is_approved": True,
    #         "type": WorkerDay.TYPE_WORKDAY,
    #         "dttm_work_start": datetime.combine(self.dt, time(10, 0, 0)),
    #         "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
    #         "worker_day_details": [{
    #             "work_part": 1.0,
    #             "work_type_id": self.work_type2.id}
    #         ]
    #     }
    #     resp = self.client.post(self.url, data, format='json')
    #     self.assertEqual(resp.status_code, 400)
    #     self.assertDictEqual(
    #         resp.json(),
    #         {
    #             "error": [
    #                 "Не существует рабочего дня в плановом подтвержденном графике. "
    #                 "Необходимо создать и подтвердить рабочий день в плановом графике, "
    #                 "или проверить, что магазины в плановом и фактическом графиках совпадают."
    #             ]
    #         },
    #     )

    def test_valid_error_message_returned_when_dt_is_none(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": None,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['dt'][0], 'Поле дата не может быть пустым.')

    def test_network_breaks(self):
        Employment.objects.all().update(position=None)
        Shop.objects.all().update(settings=None)
        dt = date.today()
        WorkerDay.objects.all().delete()
        self.employment2.refresh_from_db()
        self.shop.refresh_from_db()
        self.network.breaks = self.breaks
        self.network.save()
        wd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=dt,
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(20)),
            type=WorkerDay.TYPE_WORKDAY,
        )
        self.assertEqual(wd.work_hours, timedelta(hours=10, minutes=45))

    def test_create_and_update_with_bad_dates(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "dt": self.dt,
            "is_fact": False,
            "is_approved": False,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(18)),
            "dttm_work_end": datetime.combine(self.dt, time(2)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': ['Дата начала должна быть меньше чем дата окончания.']})
        wd = WorkerDay.objects.get(dt=self.dt, shop=self.shop, employee_id=self.employee2.id, is_approved=False, is_fact=False)
        response = self.client.put(self.url + f'{wd.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': ['Дата начала должна быть меньше чем дата окончания.']})
        data['dt'] = self.dt + timedelta(1)
        data['dttm_work_end'] = datetime.combine(self.dt, time(22))
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'non_field_errors': ['Дата начала должна быть меньше чем дата окончания.']})


class TestCropSchedule(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.dt_now = datetime.now().date()
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type = WorkType.objects.create(work_type_name=cls.work_type_name, shop=cls.shop)

        # всегда 1 ч перерыв, чтобы было легче считать
        cls.shop.network.crop_work_hours_by_shop_schedule = True
        cls.shop.network.only_fact_hours_that_in_approved_plan = False
        cls.shop.network.save()
        cls.shop.settings.breaks.value = '[[0, 2000, [30, 30]]]'
        cls.shop.settings.breaks.save()

    def _test_crop_hours(
            self, shop_open_h, shop_close_h, work_start_h, work_end_h, expected_work_h, bulk=False, crop=True):
        self.shop.tm_open_dict = f'{{"all":"{shop_open_h}:00:00"}}' if isinstance(shop_open_h, int) else shop_open_h
        self.shop.tm_close_dict = f'{{"all":"{shop_close_h}:00:00"}}' if isinstance(shop_close_h, int) else shop_close_h
        self.shop.save()

        WorkerDay.objects.filter(
            dt=self.dt_now,
            employee=self.employee2,
            is_fact=True,
            is_approved=True,
        ).delete()

        wd_kwargs = dict(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt_now,
            is_fact=True,
            is_approved=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now, time(work_start_h, 00, 0)) \
                if isinstance(work_start_h, int) else work_start_h,
            dttm_work_end=datetime.combine(self.dt_now, time(work_end_h, 00, 0))
                if isinstance(work_end_h, int) else work_end_h,
            crop_work_hours_by_shop_schedule=crop,
        )
        if bulk:
            wd_kwargs['need_count_wh'] = True
        wd = WorkerDay(**wd_kwargs)
        if bulk:
            wd = WorkerDay.objects.bulk_create([wd])[0]
        else:
            wd.save()
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd,
            work_part=1,
        )
        self.assertEqual(
            timedelta(hours=expected_work_h) if isinstance(expected_work_h, int) else expected_work_h,
            wd.work_hours
        )

    def _test_crop_both_bulk_and_original_save(self, *args, **kwargs):
        self._test_crop_hours(*args, bulk=False, **kwargs)
        self._test_crop_hours(*args, bulk=True, **kwargs)

    def test_crop_work_hours_by_shop_schedule(self):
        # параметры: час откр. магазина, час закр. магазина, час начала работы, час конца работы, ожидаемое к-во часов
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 9)
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 12, crop=False)
        self._test_crop_both_bulk_and_original_save(10, 20, 11, 19, 7)
        self._test_crop_both_bulk_and_original_save(10, 20, 11, 19, 7, crop=False)
        self._test_crop_both_bulk_and_original_save(10, 22, 10, 23, 11)
        self._test_crop_both_bulk_and_original_save(10, 22, 10, 23, 12, crop=False)
        self._test_crop_both_bulk_and_original_save(
            10, 23, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 2)
        self._test_crop_both_bulk_and_original_save(
            10, 23, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 6, crop=False)

        # круглосуточный магазин или расписание не заполнено
        self._test_crop_both_bulk_and_original_save(
            0, 0, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 6)

        # проверка по дням недели
        weekday = self.dt_now.weekday()
        self._test_crop_both_bulk_and_original_save(
            f'{{"{weekday}":"12:00:00"}}', f'{{"{weekday}":"23:00:00"}}', 10, 20, 7)

        # факт. время работы с минутами
        self._test_crop_both_bulk_and_original_save(
            10, 22,
            datetime.combine(self.dt_now, time(9, 46, 15)),
            datetime.combine(self.dt_now, time(21, 47, 23)),
            timedelta(seconds=38843),
        )
        self._test_crop_both_bulk_and_original_save(
            10, 22,
            datetime.combine(self.dt_now, time(9, 46, 15)),
            datetime.combine(self.dt_now, time(21, 47, 23)),
            timedelta(seconds=39668),
            crop=False,
        )

        # todo: ночные смены (когда-нибудь)

    def test_zero_hours_for_holiday(self):
        ShopSchedule.objects.update_or_create(
            dt=self.dt_now,
            shop=self.shop,
            defaults=dict(
                type='H',
                opens=None,
                closes=None,
                modified_by=self.user1,
            ),
        )
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 0)


class TestWorkerDayCreateFact(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        create_departments_and_users(self)

        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()
        self.work_type_name = WorkTypeName.objects.create(name='Магазин')
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)

        self.client.force_authenticate(user=self.user1)

    def test_create_fact(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved fact
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']

        # create not approved plan
        data['is_fact'] = False
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']


@override_settings(TRUST_TICK_REQUEST=True)
class TestAttendanceRecords(TestsHelperMixin, APITestCase):
    def setUp(self):
        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()

        create_departments_and_users(self)

        self.worker_day_plan_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            is_approved=True,
        )
        self.worker_day_plan_not_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            parent_worker_day=self.worker_day_plan_approved
        )
        self.worker_day_fact_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 12, 23)),
            dttm_work_end=datetime.combine(self.dt, time(20, 2, 1)),
            is_approved=True,
            parent_worker_day=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDayFactory(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 59, 1)),
            parent_worker_day=self.worker_day_fact_approved
        )

    def test_attendancerecords_update(self):
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        tm_end = datetime.combine(self.dt, time(21, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start)

        tm_start2 = datetime.combine(self.dt, time(7, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start2,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        # проверяем, что время начала рабочего дня не перезаписалось
        self.assertNotEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start2)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start)

        AttendanceRecords.objects.create(
            dttm=tm_end,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_end, tm_end)

    def test_attendancerecords_create(self):
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            employee=self.employee3,
        )
        self.assertFalse(wd.exists())
        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user3
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=False,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee3,
        )

        self.assertTrue(wd.exists())
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee3,
        )

        self.assertTrue(wd.exists())
        wd = wd.first()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(21, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user3
        )
        self.assertEqual(WorkerDay.objects.get(id=wd.id).dttm_work_end, datetime.combine(self.dt, time(21, 0, 0)))

    def test_attendancerecords_not_approved_fact_create(self):
        self.worker_day_fact_not_approved.parent_worker_day_id = self.worker_day_fact_approved.parent_worker_day_id
        self.worker_day_fact_not_approved.save()

        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee2
        )

        self.assertTrue(wd.exists())

    @override_settings(MDA_SKIP_LEAVING_TICK=False)
    def test_attendancerecords_no_fact_create(self):
        self.worker_day_fact_not_approved.delete()
        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(20, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2,
        )
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(20, 0, 0)),
            dttm_work_end=None,
            employee=self.employee2,
        )

        self.assertTrue(wd.exists())
        wd = wd.first()

        ar = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt + timedelta(days=1), time(6, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.dttm_work_end, ar.dttm)

        wd.dttm_work_end = None
        wd.save()
        ar2 = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt + timedelta(days=3), time(20, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )

        new_wd = WorkerDay.objects.filter(
            dt=self.dt + timedelta(days=3),
            is_fact=True,
            is_approved=True,
            dttm_work_start=None,
            dttm_work_end=ar2.dttm,
            employee=self.employee2
        ).first()
        self.assertIsNotNone(new_wd)
        self.assertTrue(new_wd.employment.id, self.employment2.id)

    def test_set_workday_type_for_existing_empty_types(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).update(
            type=WorkerDay.TYPE_EMPTY,
            dttm_work_start=None,
            dttm_work_end=None,
        )
        WorkerDayCashboxDetails.objects.filter(worker_day_id=self.worker_day_fact_approved.id).delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        fact_approved = WorkerDay.objects.get(id=self.worker_day_fact_approved.id)
        self.assertEqual(fact_approved.type, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(fact_approved.dttm_work_start, tm_start)
        self.assertEqual(fact_approved.dttm_work_end, None)
        fact_worker_day_details = fact_approved.worker_day_details.all()
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)

    def test_set_is_vacancy_as_True_if_shops_are_different(self):
        self.worker_day_fact_approved.delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user8
        )

        new_wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=tm_start,
            dttm_work_end=None,
            employee=self.employee8,
        ).last()
        self.assertEqual(new_wd.type, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(new_wd.dttm_work_start, tm_start)
        self.assertEqual(new_wd.dttm_work_end, None)
        self.assertEqual(new_wd.is_vacancy, True)

    def test_create_attendance_records_for_different_shops(self):
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        self.worker_day_fact_approved.refresh_from_db()
        self.assertEqual(self.worker_day_fact_approved.type, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(self.worker_day_fact_approved.dttm_work_start, tm_start)
        self.assertEqual(self.worker_day_fact_approved.dttm_work_end, None)
        self.assertEqual(self.worker_day_fact_approved.is_vacancy, True)

        tm_end = datetime.combine(self.dt, time(19, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_end,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop2,
            user=self.user2
        )
        self.worker_day_fact_approved.refresh_from_db()
        self.assertEqual(self.worker_day_fact_approved.type, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(self.worker_day_fact_approved.dttm_work_start, tm_start)
        self.assertEqual(self.worker_day_fact_approved.dttm_work_end, tm_end)
        self.assertEqual(self.worker_day_fact_approved.is_vacancy, True)

    def test_fact_work_type_received_from_plan_approved(self):
        self.worker_day_fact_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)

    def test_fact_work_type_received_from_plan_approved_when_shop_differs(self):
        self.worker_day_fact_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.select_related('work_type')
        self.assertEqual(len(plan_worker_day_details), 1)
        # shop2 wt
        WorkType.objects.create(
            shop=self.shop2,
            work_type_name=plan_worker_day_details[0].work_type.work_type_name,
        )
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2,
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertNotEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)
        self.assertEqual(
            fact_worker_day_details[0].work_type.work_type_name_id,
            plan_worker_day_details[0].work_type.work_type_name_id,
        )

    def test_fact_work_type_received_from_employment_if_there_is_no_plan(self):
        work_type_name = WorkTypeName.objects.create(
            name='Повар',
        )
        work_type_name2 = WorkTypeName.objects.create(
            name='Продавец',
        )
        work_type = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name,
        )
        work_type2 = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name2,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type,
            priority=10,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type2,
            priority=5,
        )
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, work_type.id)

    def test_work_type_created_for_holiday(self):
        work_type_name = WorkTypeName.objects.create(
            name='Повар',
        )
        work_type = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type,
            priority=10,
        )
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.worker_day_details.all().delete()
        WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).update(
            type=WorkerDay.TYPE_HOLIDAY,
            dttm_work_start=None,
            dttm_work_end=None,
        )
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, work_type.id)

    def test_dt_changed_to_prev(self):
        self.worker_day_fact_approved.delete()
        record1 = AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            type=AttendanceRecords.TYPE_COMING,
            dttm=datetime.combine(self.dt, time(17, 54)),
        )
        record2 = AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            type=AttendanceRecords.TYPE_LEAVING,
            dttm=datetime.combine(self.dt + timedelta(1), time(1, 54)),
        )
        self.assertEqual(record1.dt, self.dt)
        self.assertEqual(record2.dt, self.dt)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(wd.dttm_work_start, datetime.combine(self.dt, time(17, 54)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(self.dt + timedelta(1), time(1, 54)))


    def test_create_second_record_for_prev_day_when_prev_fact_closed(self):
        self.worker_day_fact_approved.dttm_work_start = datetime.combine(self.dt - timedelta(1), time(18, 34))
        self.worker_day_fact_approved.dttm_work_end = datetime.combine(self.dt, time(1, 2))
        self.worker_day_fact_approved.save()
        AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            dttm=datetime.combine(self.dt, time(1, 5)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).first().dttm_work_end, datetime.combine(self.dt, time(1, 5)))


    def test_create_att_record_and_update_not_approved(self):
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(11, 5)),
            type=AttendanceRecords.TYPE_COMING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee__user_id=self.user1.id).count(), 2)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, employee=self.employee1)
        wd_approved = WorkerDay.objects.get(is_approved=True, is_fact=True, employee=self.employee1)
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd_not_approved.refresh_from_db()
        wd_approved.refresh_from_db()
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_end, datetime.combine(self.dt, time(14, 54)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(19, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd_not_approved.refresh_from_db()
        wd_approved.refresh_from_db()
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_end, datetime.combine(self.dt, time(19, 54)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)

    @override_settings(MDA_SKIP_LEAVING_TICK=False)
    def test_create_record_no_replace_not_approved_fact(self):
        wd = WorkerDay.objects.create(
            dt=self.dt,
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            shop_id=self.employment1.shop_id,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(10, 5)),
            dttm_work_end=datetime.combine(self.dt, time(20, 10)),
            created_by=self.user1,
            is_fact=True,
        )
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd.refresh_from_db()
        self.assertEqual(wd.dttm_work_start, datetime.combine(self.dt, time(10, 5)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(self.dt, time(20, 10)))
        self.assertTrue(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=self.dt, employee=self.employee1).exists())

    def test_create_attendance_record_fill_employment(self):
        attr = AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(attr.employee_id, self.employment1.employee_id)
        self.assertEqual(attr.dt, self.dt)
        WorkerDay.objects.update_or_create(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            is_approved=True,
            is_fact=False,
            defaults={
                'employment': self.employment2,
                'type': WorkerDay.TYPE_WORKDAY,
                'shop_id': self.employment2.shop_id,
                'dttm_work_start': datetime.combine(self.dt, time(10, 5)),
                'dttm_work_end': datetime.combine(self.dt, time(20, 10)),
            }
        )
        attr = AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            user_id=self.employment2.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
        )
        self.assertEqual(attr.employee_id, self.employment2.employee_id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_COMING)

    def test_create_attendance_record_with_two_near_workdays(self):
        WorkerDay.objects.update_or_create(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            is_approved=True,
            is_fact=False,
            defaults={
                'employment': self.employment2,
                'type': WorkerDay.TYPE_WORKDAY,
                'shop': self.shop,
                'dttm_work_start': datetime.combine(self.dt, time(10)),
                'dttm_work_end': datetime.combine(self.dt, time(16)),
            }
        )
        self.second_employee = Employee.objects.create(
            user=self.user2,
            tabel_code='1234',
        )
        self.second_employment = Employment.objects.create(
            employee=self.second_employee,
            shop_id=self.employment2.shop_id,
        )
        WorkerDay.objects.create(
            dt=self.dt,
            employee=self.second_employee,
            is_approved=True,
            is_fact=False,
            employment=self.second_employment,
            type=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt, time(16)),
            dttm_work_end=datetime.combine(self.dt, time(22)),
        )
        attr = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(self.dt, time(15, 40)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(attr.employee_id, self.employment2.employee_id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_LEAVING)
        attr = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(self.dt, time(15, 41)),
            type=AttendanceRecords.TYPE_COMING,
        )
        self.assertEqual(attr.employee_id, self.second_employee.id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_COMING)


class TestVacancy(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/worker_day/vacancy/'
        cls.create_departments_and_users()
        cls.dt_now = date.today()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.vacancy = WorkerDay.objects.create(
            shop=cls.shop,
            employee=cls.employee1,
            employment=cls.employment1,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(20)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
        )
        cls.vacancy2 = WorkerDay.objects.create(
            shop=cls.shop,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(17)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
            is_approved=True,
        )
        cls.vac_wd_details = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy2,
            work_part=1,
        )
        cls.wd_details = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy,
            work_part=0.5,
        )
        cls.wd_details2 = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.vacancy,
            work_part=0.5,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_vacancy(self):
        data = {
            'id': None,
            'dt': Converter.convert_date(self.dt_now),
            'dttm_work_start': datetime.combine(self.dt_now, time(hour=11, minute=30)),
            'dttm_work_end': datetime.combine(self.dt_now, time(hour=20, minute=30)),
            'is_fact': False,
            'is_vacancy': True,
            'shop_id': self.shop.id,
            'type': "W",
            'worker_day_details': [
                {
                    'work_part': 1,
                    'work_type_id': self.work_type1.id
                },
            ],
            'employee_id': None
        }

        resp = self.client.post(reverse('WorkerDay-list'), data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def _test_vacancy_ordering(self, ordering_field, desc):
        if getattr(self.vacancy, ordering_field) == getattr(self.vacancy2, ordering_field):
            return

        ordering = ordering_field
        v1_first = getattr(self.vacancy, ordering_field) < getattr(self.vacancy2, ordering_field)
        if desc:
            ordering = '-' + ordering_field
            v1_first = not v1_first
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100&ordering={ordering}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], (self.vacancy if v1_first else self.vacancy2).id)
        self.assertEqual(resp.json()['results'][-1]['id'], (self.vacancy2 if v1_first else self.vacancy).id)

    def test_vacancy_ordering(self):
        for ordering_field in ['id', 'dt', 'dttm_work_start', 'dttm_work_end']:
            self._test_vacancy_ordering(ordering_field, desc=False)
            self._test_vacancy_ordering(ordering_field, desc=True)

    def test_default_dt_from_and_dt_to_filers(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dt=self.dt_now - timedelta(days=1))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dt=self.dt_now + timedelta(days=35))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 0)

        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dt=self.dt_now + timedelta(days=27))
        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 1)

    def test_default_vacancy_ordering_is_dttm_work_start_asc(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)))
        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=12, minute=30)))

        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], self.vacancy.id)

        WorkerDay.objects.filter(id=self.vacancy.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=12, minute=30)))
        WorkerDay.objects.filter(id=self.vacancy2.id).update(
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)))

        resp = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['results']), 2)
        self.assertEqual(resp.json()['results'][0]['id'], self.vacancy2.id)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 2)

    def test_get_list_shift_length(self):
        response = self.client.get(
            f'{self.url}?shop_id={self.shop.id}&shift_length_min=7:00:00&shift_length_max=9:00:00&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_get_vacant_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_vacant=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_get_outsource_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 2)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 0)
        self.vacancy2.is_outsource = True
        self.vacancy2.save()
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=true&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&is_outsource=false&limit=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_confirm_vacancy(self):
        event, _ = EventType.objects.get_or_create(
            code=VACANCY_CONFIRMED_TYPE,
            network=self.network,
        )
        subject = 'Сотрудник откликнулся на вакансию.'
        event_notification = EventEmailNotification.objects.create(
            event_type=event,
            subject=subject,
            system_email_template='notifications/email/vacancy_confirmed.html',
        )
        self.user1.email = 'test@mail.mm'
        self.user1.save()
        event_notification.users.add(self.user1)
        self.shop.__class__.objects.filter(id=self.shop.id).update(email=True)
        pnawd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now, time(hour=11, minute=30)),
            dttm_work_end=datetime.combine(self.dt_now, time(hour=20, minute=30)),
            dt=self.dt_now,
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type1,
            worker_day=pnawd,
            work_part=1,
        )
        pawd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        self.client.force_authenticate(user=self.user2)
        ShopMonthStat.objects.create(
            shop=self.shop,
            dt=now().date().replace(day=1),
            dttm_status_change=now(),
            status=ShopMonthStat.READY,
        )
        FunctionGroup.objects.create(
            group=self.employee_group,
            method='POST',
            func='WorkerDay_confirm_vacancy',
            level_up=1,
            level_down=99,
        )
        response = self.client.post(f'/rest_api/worker_day/{self.vacancy2.id}/confirm_vacancy/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, subject)
        self.assertEqual(mail.outbox[0].to[0], self.user1.email)
        body = f'Здравствуйте, {self.user1.first_name}!\n\nСотрудник {self.user2.last_name} {self.user2.first_name} откликнулся на вакансию {self.vacancy2.dt} с типом работ {self.work_type1.work_type_name.name}\n\nПисьмо отправлено роботом.'
        self.assertEqual(mail.outbox[0].body, body)

        self.assertFalse(WorkerDay.objects.filter(id=pawd.id).exists())

    def test_approve_vacancy(self):
        WorkerDay.objects.filter(id=self.vacancy.id).update(employee_id=None, is_approved=False)
        wd = WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )

        resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.vacancy.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(WorkerDay.objects.filter(id=wd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.vacancy.id, is_approved=True).exists())

        WorkerDay.objects.filter(id=self.vacancy.id).update(employee=wd.employee, is_approved=False)

        resp = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/approve_vacancy/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(WorkerDay.objects.filter(id=wd.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.vacancy.id, is_approved=True).exists())
        self.assertTrue(WorkerDay.objects.filter(
            dt=self.vacancy.dt,
            employee_id=self.vacancy.employee_id,
            is_fact=self.vacancy.is_fact,
            is_approved=True,
        ).exists())

    def test_get_only_available(self):
        '''
        Создаем дополнительно 3 вакансии на 3 дня вперед
        Вернется только одна вакансия, так как:
        1. У сотрудника подтвержденный рабочий день
        2. У сотрудника нет подтвержденного плана
        3. Сотрудник уволен до даты вакансии
        '''
        WorkerDay.objects.create(
            employee=self.employment1.employee,
            employment=self.employment1,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now,
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            employee=self.employment1.employee,
            employment=self.employment1,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(1), time(hour=11, minute=30)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(1), time(hour=20, minute=30)),
            dt=self.dt_now + timedelta(1),
            is_approved=False,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(1), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(1), time(17)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(1),
            is_vacancy=True,
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(2), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(2), time(17)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(2),
            is_vacancy=True,
            is_approved=True,
        )
        WorkerDay.objects.create(
            employee=self.employment1.employee,
            employment=self.employment1,
            type=WorkerDay.TYPE_HOLIDAY,
            dt=self.dt_now + timedelta(3),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt_now + timedelta(2), time(9)),
            dttm_work_end=datetime.combine(self.dt_now + timedelta(2), time(17)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now + timedelta(3),
            is_vacancy=True,
            is_approved=True,
        )
        self.employment1.dt_fired = self.dt_now + timedelta(2)
        self.employment1.save()
        resp = self.client.get('/rest_api/worker_day/vacancy/?only_available=true&offset=0&limit=10&is_vacant=true')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['dt'], self.dt_now.strftime('%Y-%m-%d'))



class TestAditionalFunctions(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    maxDiff = None

    def setUp(self):
        from src.timetable.models import ExchangeSettings
        super().setUp()

        self.url = '/rest_api/worker_day/'
        create_departments_and_users(self)
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)
        ExchangeSettings.objects.create(network=self.network)
        self.client.force_authenticate(user=self.user1)

    def update_or_create_holidays(self, employment, dt_from, count, approved, wds={}):
        result = {}
        for day in range(count):
            dt = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(dt, None)
            result[dt] = WorkerDay.objects.create(
                employee=employment.employee,
                employment=employment,
                shop=employment.shop,
                dt=dt,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=approved,
                parent_worker_day=parent_worker_day,
            )
        return result

    def create_worker_days(self, employment, dt_from, count, from_tm, to_tm, approved, wds={}, is_blocked=False, night_shift=False):
        result = {}
        for day in range(count):
            date = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(date, None)
            date_to = date + timedelta(1) if night_shift else date
            wd = WorkerDay.objects.create(
                employment=employment,
                employee=employment.employee,
                shop=employment.shop,
                dt=date,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(date, time(from_tm)),
                dttm_work_end=datetime.combine(date_to, time(to_tm)),
                is_approved=approved,
                parent_worker_day=parent_worker_day,
                is_blocked=is_blocked,
            )
            result[date] = wd

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        return result

    def test_delete(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 3, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        self.update_or_create_holidays(self.employment2, dt_from + timedelta(3), 1, False)

        url = f'{self.url}delete_worker_days/'
        data = {
            'employee_ids':[self.employment2.employee_id, self.employment3.employee_id],
            'dates':[
                dt_from + timedelta(i)
                for i in range(3)
            ]
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 2)
    
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
                    type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from - timedelta(days=2), is_approved=True,
                    cashbox_details__work_type__work_type_name__name='Продавец-кассир',
                    cashbox_details__work_type__work_type_name__code='consult',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from - timedelta(days=2), is_approved=True,
                )

                wd_create_user3_and_delete_user2 = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from - timedelta(days=1), is_approved=True,
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from - timedelta(days=1), is_approved=True,
                )

                wd_update_user3 = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from, is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                wd_update_user2 = WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from, is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(20, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )

                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from + timedelta(days=1), is_approved=True,
                )
                wd_create_user2_and_delete_user3 = WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=1), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from, time(11, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from, time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )

                # не рабочие дни -- не отправляется
                WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type=WorkerDay.TYPE_HOLIDAY, shop=self.shop, dt=dt_from + timedelta(days=2), is_approved=True,
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type=WorkerDay.TYPE_VACATION, shop=self.shop, dt=dt_from + timedelta(days=2), is_approved=True,
                )

                wd_create_user3_and_delete_user2_diff_work_types = WorkerDayFactory(
                    employment=self.employment2,
                    employee=self.employee2,
                    type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=3), is_approved=True,
                    dttm_work_start=datetime.combine(dt_from + timedelta(days=3), time(8, 0, 0)),
                    dttm_work_end=datetime.combine(dt_from + timedelta(days=3), time(21, 0, 0)),
                    cashbox_details__work_type__work_type_name__name='Врач',
                    cashbox_details__work_type__work_type_name__code='doctor',
                )
                WorkerDayFactory(
                    employment=self.employment3,
                    employee=self.employee3,
                    type=WorkerDay.TYPE_WORKDAY, shop=self.shop, dt=dt_from + timedelta(days=3), is_approved=True,
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
        #self.assertIsNone(data[0]['employment_id'])  # FIXME: почему должен быть None?
        self.assertEqual(data[1]['employment_id'], self.employment3.id)
        self.assertEqual(data[1]['shop_id'], self.employment3.shop.id)
        self.assertEqual(data[1]['work_hours'], '08:45:00')

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

    def test_duplicate_full(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_workerday_ids': list(WorkerDay.objects.filter(employee=self.employee2).values_list('id', flat=True)),
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
        }
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee3, is_approved=False).count(), 5)

    def test_duplicate_less(self):
        dt_from = date.today()
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        data = {
            'from_workerday_ids': list(WorkerDay.objects.filter(employee=self.employee2).values_list('id', flat=True)),
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
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
            'from_workerday_ids': list(WorkerDay.objects.filter(employee=self.employee2).values_list('id', flat=True)),
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(8)],
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
            'from_workerday_ids': list(WorkerDay.objects.filter(employee=self.employee2).values_list('id', flat=True)),
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
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
            'from_workerday_ids': list(WorkerDay.objects.filter(employee=self.employee2).values_list('id', flat=True)),
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
            'from_workerday_ids': list(WorkerDay.objects.filter(employee=self.employee2).values_list('id', flat=True)),
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from2 + timedelta(i)) for i in range(8)],
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
            'from_workerday_ids': list(WorkerDay.objects.filter(employee=self.employee2).values_list('id', flat=True)),
            'to_employee_id': self.employee3.id,
            'to_dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
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
            type=WorkerDay.TYPE_WORKDAY,
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
            type=WorkerDay.TYPE_HOLIDAY,
            is_fact=False,
            is_approved=False,
        )

        data = {
            'from_workerday_ids': [wd_dt_now.id, wd_dt_tomorrow.id],
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
            employee=self.employee3, is_approved=False, dt=dt_to + timedelta(days=1), type='W'
        ).count(), 1)

    def test_copy_approved(self):
        dt_now = date.today()
        self.create_worker_days(self.employment1, dt_now, 3, 10, 20, True)
        self.update_or_create_holidays(self.employment1, dt_now + timedelta(days=3), 3, True)
        WorkerDay.objects.create(
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            type=WorkerDay.TYPE_WORKDAY,
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
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 12)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)

    def test_copy_approved_to_fact(self):
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
            type=WorkerDay.TYPE_EMPTY,
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
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, type=WorkerDay.TYPE_HOLIDAY).count(), 0)
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
            type=WorkerDay.TYPE_WORKDAY,
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
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True).count(), 7)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, is_fact=True, type=WorkerDay.TYPE_HOLIDAY).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, employee_id=self.employment2.employee_id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=False, dt=dt_now + timedelta(days=6)).count(), 0)

    def test_copy_range(self):
        dt_from_first = date.today().replace(day=1)
        dt_from_last = dt_from_first + relativedelta(day=31)
        dt_to_first = dt_from_first + relativedelta(months=1)
        dt_to_last = dt_to_first + relativedelta(day=31)

        for i in range((dt_from_last - dt_from_first).days + 1):
            dt = dt_from_first + timedelta(i)
            type = WorkerDay.TYPE_WORKDAY if i % 3 != 0 else WorkerDay.TYPE_HOLIDAY
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment2.shop_id,
                employee_id=self.employment2.employee_id,
                employment=self.employment2,
                type=type,
                is_approved=True,
            )
            if i % 2 == 0 and i < 28:
                WorkerDay.objects.create(
                    dt=dt,
                    shop_id=self.employment2.shop_id,
                    employee_id=self.employment2.employee_id,
                    employment=self.employment2,
                    type=WorkerDay.TYPE_WORKDAY,
                    is_approved=True,
                    is_fact=True,
                )
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment3.shop_id,
                employee_id=self.employment3.employee_id,
                employment=self.employment3,
                type=type,
                is_approved=True,
            )
            WorkerDay.objects.create(
                dt=dt,
                shop_id=self.employment4.shop_id,
                employee_id=self.employment4.employee_id,
                employment=self.employment4,
                type=type,
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
        }
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), ((dt_from_last - dt_from_first).days + 1) * 3 + 14)
        response = self.client.post(self.url + 'copy_range/', data=data)
        response_data = response.json()

        self.assertEqual(len(response_data), ((dt_to_last - dt_to_first).days + 1) * 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False, dt__gte=dt_to_first, dt__lte=dt_to_last).count(), ((dt_to_last - dt_to_first).days + 1) * 2)
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
            type=WorkerDay.TYPE_WORKDAY,
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
            type=WorkerDay.TYPE_WORKDAY,
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

    # def test_change_list(self):
    #     dt_from = date.today()
    #     data = {
    #         'shop_id': self.shop.id,
    #         'workers': {
    #             self.user2.id: [
    #                 Converter.convert_date(dt_from),
    #                 Converter.convert_date(dt_from + timedelta(1)),
    #                 Converter.convert_date(dt_from + timedelta(3)),
    #             ],
    #             self.user3.id: [
    #                 Converter.convert_date(dt_from),
    #                 Converter.convert_date(dt_from + timedelta(2)),
    #                 Converter.convert_date(dt_from + timedelta(3)),
    #             ],
    #         },
    #         'type': WorkerDay.TYPE_WORKDAY,
    #         'tm_work_start': '10:00:00',
    #         'tm_work_end': '22:00:00',
    #         'work_type': self.work_type.id,
    #         'comment': 'Test change',
    #     }
    #     wds = self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
    #     self.create_worker_days(self.employment2, dt_from, 2, 10, 20, False, wds=wds)
    #     wds = self.create_worker_days(self.employment2, dt_from, 3, 10, 20, True)
    #     wds.update(self.update_or_create_holidays(self.employment3, dt_from + timedelta(3), 1, True))
    #     self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False, wds=wds)
    #     self.update_or_create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
    #     url = f'{self.url}change_list/'
    #     response = self.client.post(url, data, format='json')
    #     data = response.json()
    #     self.assertEqual(len(data), 2)
    #     self.assertEqual(len(data[str(self.user2.id)]), 3)
    #     self.assertEqual(len(data[str(self.user3.id)]), 3)
