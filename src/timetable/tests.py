from datetime import timedelta, time, datetime, date

from django.core import mail
from django.urls import reverse
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import FunctionGroup, Network
from src.timetable.models import (
    WorkerDay,
    AttendanceRecords,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    ShopMonthStat,
)
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter
from src.util.test import create_departments_and_users


class TestWorkerDay(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()

        create_departments_and_users(self)
        self.work_type_name = WorkTypeName.objects.create(name='Магазин', network=self.network)
        self.work_type = WorkType.objects.create(
            work_type_name=self.work_type_name,
            shop=self.shop)

        self.worker_day_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
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
            worker=self.user2,
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
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 12, 23)),
            dttm_work_end=datetime.combine(self.dt, time(20, 2, 1)),
            is_approved=True,
            parent_worker_day=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 59, 1)),
            parent_worker_day=self.worker_day_fact_approved
        )

        FunctionGroup.objects.bulk_create([
            FunctionGroup(group=self.admin_group,
                method=method,
                func=func,
                level_up=1,
                level_down=99,
            )  for method in ['POST','PUT','DELETE'] for func in ['WorkerDay', 'WorkerDay_approve']
            ])

        self.client.force_authenticate(user=self.user1)

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
            'worker_id': self.user2.id,
            'employment_id': self.employment2.id,
            'is_fact': False,
            'is_approved': False,
            'type': WorkerDay.TYPE_WORKDAY,
            'parent_worker_day_id': self.worker_day_plan_approved.id,
            'comment': None,
            'dt': Converter.convert_date(self.dt),
            'dttm_work_start': Converter.convert_datetime(datetime.combine(self.dt, time(8, 0, 0))),
            'dttm_work_end': Converter.convert_datetime(datetime.combine(self.dt, time(20, 0, 0))),
            'work_hours': '10:45:00',
            'worker_day_details': [],
            'is_outsource': False,
            'is_vacancy': False,
        }

        self.assertEqual(response.json(), data)

    def test_approve(self):
        # Approve plan
        data = {
            'shop_id': self.shop.id,
            'dt_from': self.dt,
            'dt_to': self.dt + timedelta(days=2),
            'is_fact': False,
        }
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).is_approved, True)
        self.assertIsNone(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).parent_worker_day_id)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).exists())
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).parent_worker_day_id,
                         self.worker_day_plan_not_approved.id)

        # Approve fact
        data['is_fact'] = True

        # plan(approved) <- fact0(approved) <- fact1(not approved) ==> plan(approved) <- fact1(approved)
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id,
                         self.worker_day_plan_not_approved.id)

    # Последовательное создание и подтверждение P1 -> A1 -> P2 -> F1 -> A2 -> F2
    def test_create_and_approve(self):
        dt = self.dt + timedelta(days=1)

        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
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

        # create not approved fact
        data['is_fact'] = True
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']
        parent_id = response.json()['parent_worker_day_id']
        self.assertEqual(parent_id, plan_id)

        # edit not approved plan
        data_holiday = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": dt,
            "is_fact": False,
            "type": WorkerDay.TYPE_HOLIDAY,
        }

        response = self.client.put(f"{self.url}{plan_id}/", data_holiday, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], plan_id)
        self.assertEqual(response.json()['type'], data_holiday['type'])

        # edit not approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(7, 48, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(20, 2, 0)))

        response = self.client.put(f"{self.url}{fact_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], fact_id)
        self.assertEqual(response.json()['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(response.json()['dttm_work_end'], data['dttm_work_end'])

        # Approve plan
        data_approve = {
            'shop_id': self.shop.id,
            'dt_from': dt,
            'dt_to': dt + timedelta(days=2),
            'is_fact': False,
        }

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=plan_id).is_approved, True)
        self.assertEqual(WorkerDay.objects.get(id=fact_id).is_approved, False)

        # Approve fact
        data_approve['is_fact'] = True

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=fact_id).is_approved, True)

        # edit approved plan
        data['is_fact'] = False
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_plan_id = response.json()['id']
        new_plan = WorkerDay.objects.get(id=new_plan_id)
        self.assertNotEqual(new_plan_id, plan_id)
        self.assertEqual(response.json()['parent_worker_day_id'], plan_id)
        self.assertEqual(response.json()['type'], data['type'])

        # edit approved plan again
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

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
        self.assertEqual(WorkerDay.objects.get(id=new_fact_id).parent_worker_day_id, fact_id)
        self.assertEqual(res['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(res['dttm_work_end'], data['dttm_work_end'])

        # edit approved fact again
        response = self.client.post(f"{self.url}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': f"У сотрудника уже существует рабочий день."})

    def test_empty_params(self):
        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
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
            "worker_id": self.user2.id,
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
            "worker_id": self.user2.id,
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
            "worker_id": self.user2.id,
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
            'is_tabel': 'true',
            'dt__gte': (self.dt - timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt__lte': self.dt.strftime('%Y-%m-%d'),
        }
        response = self.client.get('/rest_api/worker_day/', data=get_params)
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)
        self.assertEqual(resp_data[0]['type'], 'S')

    def test_get_worker_day_by_worker__username__in(self):
        get_params = {
            'worker__username__in': self.user2.username,
            'is_fact': 'true',
            'is_approved': 'true',
            'dt__gte': (self.dt - timedelta(days=5)).strftime('%Y-%m-%d'),
            'dt__lte': self.dt.strftime('%Y-%m-%d'),
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
            "is_fact": 'true',
            "type": WorkerDay.TYPE_HOLIDAY,
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
        response = self.client.put(f"{self.url}{wd_id}/", data, format='json')
        self.assertEqual(response.status_code, 200)


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

        FunctionGroup.objects.bulk_create([
            FunctionGroup(group=self.admin_group,
                          method=method,
                          func=func,
                          level_up=1,
                          level_down=99,
                          ) for method in ['POST', 'PUT', 'DELETE'] for func in ['WorkerDay', 'WorkerDayApprove']
        ])
        self.client.force_authenticate(user=self.user1)

    def test_create_fact(self):
        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
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


class TestAttendanceRecords(TestsHelperMixin, APITestCase):
    def setUp(self):
        self.url = '/rest_api/worker_day/'
        self.url_approve = '/rest_api/worker_day/approve/'
        self.dt = now().date()

        create_departments_and_users(self)

        self.worker_day_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
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
            worker=self.user2,
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
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=True,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 12, 23)),
            dttm_work_end=datetime.combine(self.dt, time(20, 2, 1)),
            is_approved=True,
            parent_worker_day=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
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

        # проверяем, что время начала рабочего дня не перезаписалась
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
            worker=self.user3
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
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            worker=self.user3
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
            worker=self.user2
        )

        self.assertTrue(wd.exists())
        wd = wd.first()
        self.assertEqual(wd.parent_worker_day_id, self.worker_day_plan_approved.id)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id, wd.id)

    def test_attendancerecords_no_fact_create(self):
        self.worker_day_fact_not_approved.delete()
        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )
        #
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            worker=self.user2
        )

        self.assertTrue(wd.exists())
        wd = wd.first()
        self.assertEqual(wd.parent_worker_day_id, self.worker_day_plan_approved.id)


class TestVacancy(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/worker_day/vacancy/'
        cls.create_departments_and_users()
        cls.dt_now = date.today()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        cls.network = Network.objects.create(
            primary_color='#BDF82',
            secondary_color='#390AC',
        )
        cls.shop.network = cls.network
        cls.shop.save()
        cls.user2.network = cls.network
        cls.user2.save()
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.worker_day = WorkerDay.objects.create(
            shop=cls.shop,
            worker=cls.user1,
            employment=cls.employment1,
            dttm_work_start=datetime.combine(cls.dt_now, time(9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(20)),
            type=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            is_vacancy=True,
        )
        cls.vacancy = WorkerDay.objects.create(
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
            worker_day=cls.vacancy,
            work_part=1,
        )
        cls.wd_details = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.worker_day,
            work_part=0.5,
        )
        cls.wd_details2 = WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.worker_day,
            work_part=0.5,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_vacancy(self):
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='WorkerDay',
            level_up=0,
            level_down=99,
        )

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
            'worker_id': None
        }

        resp = self.client.post(reverse('WorkerDay-list'), data=data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

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

    def test_confirm_vacancy(self):
        self.shop.__class__.objects.filter(id=self.shop.id).update(email=True)
        pnawd = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
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
            worker=self.user2,
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
        response = self.client.post(f'/rest_api/worker_day/{self.vacancy.id}/confirm_vacancy/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'result': 'Вакансия успешно принята.'})

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Изменение в графике выхода сотрудников')

        self.assertFalse(WorkerDay.objects.filter(id=pawd.id).exists())


class TestAditionalFunctions(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

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
        FunctionGroup.objects.bulk_create([
            FunctionGroup(group=self.admin_group,
                          method=method,
                          func=func,
                          level_up=1,
                          level_down=99,
                          ) for method in ['POST', 'PUT', 'DELETE']
            for func in
            ['WorkerDay_change_list', 'WorkerDay_duplicate', 'WorkerDay_delete_timetable', 'WorkerDay_exchange']
        ])
        self.client.force_authenticate(user=self.user1)

    def create_holidays(self, employment, dt_from, count, approved, wds={}):
        result = {}
        for day in range(count):
            dt = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(dt, None)
            result[dt] = WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
                shop=employment.shop,
                dt=dt,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=approved,
                parent_worker_day=parent_worker_day,
            )
        return result

    def create_worker_days(self, employment, dt_from, count, from_tm, to_tm, approved, wds={}):
        result = {}
        for day in range(count):
            date = dt_from + timedelta(days=day)
            parent_worker_day = None if approved else wds.get(date, None)
            wd = WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
                shop=employment.shop,
                dt=date,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(date, time(from_tm)),
                dttm_work_end=datetime.combine(date, time(to_tm)),
                is_approved=approved,
                parent_worker_day=parent_worker_day,
            )
            result[date] = wd

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type,
                worker_day=wd
            )
        return result

    def test_delete_all(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'dt_from': Converter.convert_date(dt_from),
            'dt_to': Converter.convert_date(dt_from + timedelta(4)),
            'delete_all': True,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 4, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        url = f'{self.url}delete_timetable/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        # остаётся 4 т.к. у сотрудника auto_timetable=False
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 4)

    def test_delete(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'dt_from': Converter.convert_date(dt_from),
            'dt_to': Converter.convert_date(dt_from + timedelta(4)),
            'types': ['W', ],
            'users': [self.user2.id, self.user3.id],
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 3, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        self.create_holidays(self.employment2, dt_from + timedelta(3), 1, False)
        url = f'{self.url}delete_timetable/'
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 8)
        # остаётся 1 выходной т.к. удаляем только рабочие дни
        self.assertEqual(WorkerDay.objects.filter(is_approved=False).count(), 1)

    def test_exchange_approved(self):
        dt_from = date.today()
        data = {
            'worker1_id': self.user2.id,
            'worker2_id': self.user3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
            'is_approved': True,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        url = f'{self.url}exchange/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)

    def test_exchange_not_approved(self):
        dt_from = date.today()
        data = {
            'worker1_id': self.user2.id,
            'worker2_id': self.user3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(4)],
            'is_approved': False,
        }
        self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 4, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False)
        url = f'{self.url}exchange/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 8)

    def test_duplicate_approved(self):
        dt_from = date.today()
        data = {
            'from_worker_id': self.user2.id,
            'to_worker_id': self.user3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': True,
        }
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        self.create_worker_days(self.employment3, dt_from, 4, 9, 21, False)
        self.create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)

    def test_duplicate_not_approved(self):
        dt_from = date.today()
        data = {
            'from_worker_id': self.user2.id,
            'to_worker_id': self.user3.id,
            'dates': [Converter.convert_date(dt_from + timedelta(i)) for i in range(5)],
            'is_approved': False,
        }
        self.create_worker_days(self.employment2, dt_from, 5, 10, 20, True)
        wds = self.create_worker_days(self.employment3, dt_from, 4, 9, 21, True)
        self.create_worker_days(self.employment2, dt_from, 5, 16, 20, False)
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False, wds=wds)
        self.create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        url = f'{self.url}duplicate/'
        response = self.client.post(url, data, format='json')
        self.assertEqual(len(response.json()), 5)

    def test_change_list(self):
        dt_from = date.today()
        data = {
            'shop_id': self.shop.id,
            'workers': {
                self.user2.id: [
                    Converter.convert_date(dt_from),
                    Converter.convert_date(dt_from + timedelta(1)),
                    Converter.convert_date(dt_from + timedelta(3)),
                ],
                self.user3.id: [
                    Converter.convert_date(dt_from),
                    Converter.convert_date(dt_from + timedelta(2)),
                    Converter.convert_date(dt_from + timedelta(3)),
                ],
            },
            'type': WorkerDay.TYPE_WORKDAY,
            'tm_work_start': '10:00:00',
            'tm_work_end': '22:00:00',
            'work_type': self.work_type.id,
            'comment': 'Test change',
        }
        wds = self.create_worker_days(self.employment2, dt_from, 4, 10, 20, True)
        self.create_worker_days(self.employment2, dt_from, 2, 10, 20, False, wds=wds)
        wds = self.create_worker_days(self.employment2, dt_from, 3, 10, 20, True)
        wds.update(self.create_holidays(self.employment3, dt_from + timedelta(3), 1, True))
        self.create_worker_days(self.employment3, dt_from, 4, 10, 21, False, wds=wds)
        self.create_holidays(self.employment3, dt_from + timedelta(4), 1, False)
        url = f'{self.url}change_list/'
        response = self.client.post(url, data, format='json')
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(len(data[str(self.user2.id)]), 3)
        self.assertEqual(len(data[str(self.user3.id)]), 3)
