from datetime import timedelta, time, datetime

from django.utils.timezone import now

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.timetable.models import WorkerDay
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

        # self.worker_day_approves = WorkerDayApprove.objects.bulk_create([
        #     WorkerDayApprove(
        #         shop=self.shop,
        #         created_by=self.user1,
        #         dt_from=self.dt,
        #         dt_to=self.dt + timedelta(days=2),
        #         is_fact=False,
        #     ),
        #     WorkerDayApprove(
        #         shop=self.shop,
        #         created_by=self.user1,
        #         dt_from=self.dt,
        #         dt_to=self.dt + timedelta(days=2),
        #         is_fact=True,
        #     )
        # ])

        self.worker_day_plan_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user2,
            employment=self.employment2,
            dt=self.dt,
            is_fact=False,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8,0,0)),
            dttm_work_end = datetime.combine(self.dt, time(20,0,0)),
            # worker_day_approve=self.worker_day_approves[0],
            is_approved=True,
        )
        self.worker_day_plan_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user3,
            employment=self.employment3,
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
            # worker_day_approve=self.worker_day_approves[0],
            parent_worker_day=self.worker_day_plan_approved,
        )
        self.worker_day_fact_not_approved = WorkerDay.objects.create(
            shop=self.shop,
            worker=self.user3,
            employment=self.employment3,
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

    # def test_get(self):
    #     response = self.client.get(f'{self.url}{self.worker_days[0].id}/')
    #     self.assertEqual(response.status_code, status.HTTP_200_OK)
    #     data = {
    #         'id': self.worker_days[0].id,
    #         # 'priority': 100,
    #         # 'dttm_last_update_queue': None,
    #         # 'min_workers_amount': 0,
    #         # 'max_workers_amount': 20,
    #         # 'probability': 1.0,
    #         # 'prior_weight': 1.0,
    #         # 'shop_id': self.shop.id,
    #         # 'worker_day_name': {
    #         #     'id': self.worker_day_name1.id,
    #         #     'name': self.worker_day_name1.name,
    #         #     'code': self.worker_day_name1.code,
    #         # },
    #     }
    #     self.assertEqual(response.json(), data)

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
        self.assertIsNotNone(WorkerDay.objects.get(id=self.worker_day_plan_approved.id).dttm_deleted)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).parent_worker_day_id, self.worker_day_plan_not_approved.id)

        # Approve fact
        data['is_fact'] = True

        # plan(approved) <- fact0(approved) <- fact1(not approved) ==> plan(approved) <- fact1(approved)
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertIsNotNone(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_deleted)
        self.assertIsNone(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).dttm_deleted)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id, self.worker_day_plan_not_approved.id)

    def test_create_and_approve(self):
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
        self.assertIsNotNone(WorkerDay.objects.get(id=self.worker_day_plan_approved.id).dttm_deleted)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).parent_worker_day_id, self.worker_day_plan_not_approved.id)

        # Approve fact
        data['is_fact'] = True

        # plan(approved) <- fact0(approved) <- fact1(not approved) ==> plan(approved) <- fact1(approved)
        response = self.client.post(self.url_approve, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # id = response.json()['id']
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).is_approved, True)
        self.assertIsNotNone(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_deleted)
        self.assertIsNone(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).dttm_deleted)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).parent_worker_day_id, self.worker_day_plan_not_approved.id)

    # def test_create_and_approve(self):
    #     data = {
    #         'code': self.worker_day_name3.code,
    #         'priority': 100,
    #         'dttm_last_update_queue': None,
    #         'min_workers_amount': 0,
    #         'max_workers_amount': 20,
    #         'probability': 1.0,
    #         'prior_weight': 1.0,
    #         'shop_id': self.shop.id,
    #     }
    #     response = self.client.post(self.url, data, format='json')
    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #     worker_day = response.json()
    #     data['id'] = worker_day['id']
    #     data['worker_day_name'] = {
    #         'id': self.worker_day_name3.id,
    #         'code': self.worker_day_name3.code,
    #         'name': self.worker_day_name3.name,
    #     }
    #     data.pop('code')
    #     self.assertEqual(worker_day, data)
    #
    # def test_create_with_id(self):
    #     data = {
    #         'worker_day_name_id': self.worker_day_name3.id,
    #         'priority': 100,
    #         'dttm_last_update_queue': None,
    #         'min_workers_amount': 0,
    #         'max_workers_amount': 20,
    #         'probability': 1.0,
    #         'prior_weight': 1.0,
    #         'shop_id': self.shop.id,
    #     }
    #     response = self.client.post(self.url, data, format='json')
    #     self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    #     worker_day = response.json()
    #     data['id'] = worker_day['id']
    #     data['worker_day_name'] = {
    #         'id': self.worker_day_name3.id,
    #         'code': self.worker_day_name3.code,
    #         'name': self.worker_day_name3.name,
    #     }
    #     data.pop('worker_day_name_id')
    #     self.assertEqual(worker_day, data)
    #
    # def test_update_by_code(self):
    #     data = {
    #         'min_workers_amount': 30,
    #         'code': self.worker_day_name3.code,
    #     }
    #     response = self.client.put(f'{self.url}{self.worker_day1.id}/', data, format='json')
    #     worker_day = response.json()
    #     data = {
    #         'id': self.worker_day1.id,
    #         'priority': 100,
    #         'dttm_last_update_queue': None,
    #         'min_workers_amount': 30,
    #         'max_workers_amount': 20,
    #         'probability': 1.0,
    #         'prior_weight': 1.0,
    #         'shop_id': self.shop.id,
    #         'worker_day_name': {
    #             'id': self.worker_day_name3.id,
    #             'code': self.worker_day_name3.code,
    #             'name': self.worker_day_name3.name,
    #         }
    #     }
    #     self.assertEqual(worker_day, data)
    #
    # def test_update_by_id(self):
    #     data = {
    #         'max_workers_amount': 30,
    #         'worker_day_name_id': self.worker_day_name3.id,
    #     }
    #     response = self.client.put(f'{self.url}{self.worker_day1.id}/', data, format='json')
    #     worker_day = response.json()
    #     data = {
    #         'id': self.worker_day1.id,
    #         'priority': 100,
    #         'dttm_last_update_queue': None,
    #         'min_workers_amount': 0,
    #         'max_workers_amount': 30,
    #         'probability': 1.0,
    #         'prior_weight': 1.0,
    #         'shop_id': self.shop.id,
    #         'worker_day_name': {
    #             'id': self.worker_day_name3.id,
    #             'code': self.worker_day_name3.code,
    #             'name': self.worker_day_name3.name,
    #         }
    #     }
    #     self.assertEqual(worker_day, data)
    #
    def test_delete(self):
        # План подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': 'Нельзя удалить подтвержденную версию'})

        # План неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_plan_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(WorkerDay.objects.get(id=self.worker_day_plan_not_approved.id).dttm_deleted)

        # Факт подтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'error': 'Нельзя удалить подтвержденную версию'})

        # Факт неподтвержденный
        response = self.client.delete(f'{self.url}{self.worker_day_fact_not_approved.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(WorkerDay.objects.get(id=self.worker_day_fact_not_approved.id).dttm_deleted)
