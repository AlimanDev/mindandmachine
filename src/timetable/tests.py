from datetime import timedelta, time, datetime

from django.utils.timezone import now

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.timetable.models import WorkerDay, AttendanceRecords, WorkType, WorkTypeName
from src.base.models import FunctionGroup
from src.util.models_converter import Converter

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
        self.work_type_name = WorkTypeName.objects.create(name='Магазин')
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
            dttm_work_start=datetime.combine(self.dt, time(8,0,0)),
            dttm_work_end = datetime.combine(self.dt, time(20,0,0)),
            is_approved=True,
        )
        self.worker_day_plan_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt,time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt,time(20, 0, 0)),
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
        dt=Converter.convert_date(self.dt)

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
            'work_hours': '12:00:00',
            'worker_day_details': [],
        }

        self.assertEqual(response.json(), data)

    def test_approve(self):
        #Approve plan
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
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).parent_worker_day_id, self.worker_day_plan_not_approved.id)

        # Approve fact
        data['is_fact'] = True

        # plan(approved) <- fact0(approved) <- fact1(not approved) ==> plan(approved) <- fact1(approved)
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id, self.worker_day_plan_not_approved.id)

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
            "dttm_work_start": datetime.combine(dt, time(8,0,0)),
            "dttm_work_end":  datetime.combine(dt, time(20,0,0)),
            "worker_day_details": [{
                "dttm_from":datetime.combine(self.dt, time(8,0,0)),
                "dttm_to":datetime.combine(self.dt, time(20,0,0)),
                 "work_type_id":self.work_type.id}
            ]
        }

        #create not approved plan
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']

        #create not approved fact
        data['is_fact'] = True
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']
        parent_id = response.json()['parent_worker_day_id']
        self.assertEqual(parent_id, plan_id)

        #edit not approved plan
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

        #edit not approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(7,48,0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(20,2,0)))

        response = self.client.put(f"{self.url}{fact_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], fact_id)
        self.assertEqual(response.json()['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(response.json()['dttm_work_end'], data['dttm_work_end'])

        #Approve plan
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

        #Approve fact
        data_approve['is_fact'] = True

        response = self.client.post(self.url_approve, data_approve, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkerDay.objects.get(id=fact_id).is_approved, True)

        # edit approved plan
        # data['is_fact'] = False
        response = self.client.put(f"{self.url}{plan_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_plan_id=response.json()['id']
        self.assertNotEqual(new_plan_id, plan_id)
        self.assertEqual(response.json()['parent_worker_day_id'], plan_id)
        self.assertEqual(response.json()['type'], data['type'])

        # edit approved fact
        data['dttm_work_start'] = Converter.convert_datetime(datetime.combine(dt, time(8, 8, 0)))
        data['dttm_work_end'] = Converter.convert_datetime(datetime.combine(dt, time(21, 2, 0)))

        response = self.client.put(f"{self.url}{fact_id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        res = response.json()
        new_fact_id = res['id']
        self.assertNotEqual(new_fact_id, fact_id)
        self.assertEqual(WorkerDay.objects.get(id=new_fact_id).parent_worker_day_id, fact_id)
        self.assertEqual(res['dttm_work_start'], data['dttm_work_start'])
        self.assertEqual(res['dttm_work_end'], data['dttm_work_end'])

    def test_empty_params(self):
        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8,0,0)),
            "dttm_work_end":  datetime.combine(self.dt, time(20,0,0)),
            "worker_day_details":[]
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {
            'error': ['dttm_work_start, dttm_work_end, and worker_day_details required for type W']})

        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_WORKDAY,
            # "dttm_work_start": None,
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "dttm_from":datetime.combine(self.dt, time(8,0,0)),
                "dttm_to":datetime.combine(self.dt, time(20,0,0)),
                 "work_type_id":self.work_type.id}]
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {
            'error': ['dttm_work_start, dttm_work_end, and worker_day_details required for type W']})

    def test_edit_approved_wd_secondly(self):
        data = {
            "shop_id": self.shop.id,
            "worker_id": self.user2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8,0,0)),
            "dttm_work_end":  datetime.combine(self.dt, time(20,0,0)),
            "worker_day_details": [{
                "dttm_from":datetime.combine(self.dt, time(8,0,0)),
                "dttm_to":datetime.combine(self.dt, time(20,0,0)),
                 "work_type_id":1}
            ]
        }

        response = self.client.put(f"{self.url}{self.worker_day_plan_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': 'У расписания уже есть неподтвержденная версия.'})

        response = self.client.put(f"{self.url}{self.worker_day_fact_approved.id}/", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': 'У расписания уже есть неподтвержденная версия.'})


    def test_delete(self):
        # План подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': 'Нельзя удалить подтвержденную версию'})

        # План неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_plan_not_approved.id).exists())

        # Факт подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': 'Нельзя удалить подтвержденную версию'})

        # Факт неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WorkerDay.objects.filter(id=self.worker_day_fact_not_approved.id).exists())


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
            "dttm_work_start": datetime.combine(self.dt, time(8,0,0)),
            "dttm_work_end": datetime.combine(self.dt, time(20,0,0)),
            "worker_day_details": [{
                "dttm_from": datetime.combine(self.dt, time(8, 0, 0)),
                "dttm_to": datetime.combine(self.dt, time(20, 0, 0)),
                "work_type_id": self.work_type.id}
            ]
        }

        #create not approved fact
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']

        #create not approved plan
        data['is_fact'] = False
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']
        parent_id = response.json()['parent_worker_day_id']
        self.assertEqual(parent_id, None)

        self.assertEqual(WorkerDay.objects.get(id=fact_id).parent_worker_day_id, plan_id)


class TestAttendanceRecords(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

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
        tm_start=datetime.combine(self.dt, time(6,0,0))
        tm_end=datetime.combine(self.dt, time(21,0,0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        # wd = WorkerDay.objects.get(
        #     dt=self.dt,
        #     is_fact=True,
        #     is_approved=True,
        #     dttm_work_start = datetime.combine(self.dt, time(6,0,0)),
        #     # dttm_work_end = None
        # )
        # # self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, datetime.combine(self.dt, time(6,0,0)))


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
            dttm=datetime.combine(self.dt, time(6,0,0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user3
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start = datetime.combine(self.dt, time(6,0,0)),
            dttm_work_end = None,
            worker=self.user3
        )

        self.assertTrue(wd.exists())
        wd=wd.first()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(21,0,0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user3
        )
        self.assertEqual(WorkerDay.objects.get(id=wd.id).dttm_work_end, datetime.combine(self.dt, time(21,0,0)))

    def test_attendancerecords_not_approved_fact_create(self):
        self.worker_day_fact_not_approved.parent_worker_day_id=self.worker_day_fact_approved.parent_worker_day_id
        self.worker_day_fact_not_approved.save()

        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6,0,0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start = datetime.combine(self.dt, time(6,0,0)),
            dttm_work_end = None,
            worker=self.user2
        )

        self.assertTrue(wd.exists())
        wd=wd.first()
        self.assertEqual(wd.parent_worker_day_id,self.worker_day_plan_approved.id)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id,wd.id)

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