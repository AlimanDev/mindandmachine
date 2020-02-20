from datetime import datetime
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.timetable.models import WorkTypeName, WorkType
from src.base.models import FunctionGroup


class TestWorkType(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/work_type/'

        create_departments_and_users(self)
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        self.work_type1 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name1)
        self.work_type2 = WorkType.objects.create(shop=self.shop2, work_type_name=self.work_type_name1)
        self.work_type_name2 = WorkTypeName.objects.create(
            name='Тип_кассы_2',
        )
        self.work_type3 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name2)
        self.work_type_name3 = WorkTypeName.objects.create(
            name='Тип_кассы_3',
            code='25',
        )
        self.work_type_name4 = WorkTypeName.objects.create(
            name='тип_кассы_4',
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='WorkType',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='WorkType',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='DELETE',
            func='WorkType',
            level_up=1,
            level_down=99,
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}')
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.work_type1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.work_type1.id,
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id, 
            'work_type_name': {
                'id': self.work_type_name1.id,
                'name': self.work_type_name1.name,
                'code': self.work_type_name1.code,
            },
        }
        self.assertEqual(response.json(), data)

    def test_create_with_code(self):
        data = {
            'code': self.work_type_name3.code,
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        work_type = response.json()
        data['id'] = work_type['id']
        data['work_type_name'] = {
            'id': self.work_type_name3.id,
            'code': self.work_type_name3.code,
            'name': self.work_type_name3.name,
        }
        data.pop('code')
        self.assertEqual(work_type, data)

    def test_create_with_id(self):
        data = {
            'work_type_name_id': self.work_type_name3.id,
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        work_type = response.json()
        data['id'] = work_type['id']
        data['work_type_name'] = {
            'id': self.work_type_name3.id,
            'code': self.work_type_name3.code,
            'name': self.work_type_name3.name,
        }
        data.pop('work_type_name_id')
        self.assertEqual(work_type, data)

    def test_update_by_code(self):
        data = {
            'min_workers_amount': 30,
            'code': self.work_type_name3.code,
        }
        response = self.client.put(f'{self.url}{self.work_type1.id}/', data, format='json')
        work_type = response.json()
        data = {
            'id': self.work_type1.id, 
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 30, 
            'max_workers_amount': 20, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id, 
            'work_type_name': {
                'id': self.work_type_name3.id,
                'code': self.work_type_name3.code,
                'name': self.work_type_name3.name,
            }
        }
        self.assertEqual(work_type, data)

    def test_update_by_id(self):
        data = {
            'max_workers_amount': 30,
            'work_type_name_id': self.work_type_name3.id,
        }
        response = self.client.put(f'{self.url}{self.work_type1.id}/', data, format='json')
        work_type = response.json()
        data = {
            'id': self.work_type1.id, 
            'priority': 100, 
            'dttm_last_update_queue': None, 
            'min_workers_amount': 0, 
            'max_workers_amount': 30, 
            'probability': 1.0, 
            'prior_weight': 1.0, 
            'shop_id': self.shop.id, 
            'work_type_name': {
                'id': self.work_type_name3.id,
                'code': self.work_type_name3.code,
                'name': self.work_type_name3.name,
            }
        }
        self.assertEqual(work_type, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.work_type1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(WorkType.objects.get(id=self.work_type1.id).dttm_deleted)
    