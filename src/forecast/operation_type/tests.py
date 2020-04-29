from datetime import datetime
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.forecast.models import OperationTypeName, OperationType
from src.timetable.models import WorkTypeName, WorkType
from src.base.models import FunctionGroup


class TestOperationType(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/operation_type/'

        create_departments_and_users(self)
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        self.work_type1 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name1)
        self.work_type2 = WorkType.objects.create(shop=self.shop2, work_type_name=self.work_type_name1)
        self.work_type3 = WorkType.objects.create(shop=self.shop3, work_type_name=self.work_type_name1)

        self.operation_type_name1 = OperationTypeName.objects.create(
            name='продажа',
        )
        self.operation_type_name2 = OperationTypeName.objects.create(
            name='продажа2',
        )
        self.operation_type_name3 = OperationTypeName.objects.create(
            name='продажа3',
            code='3',
        )

        self.operation_type = OperationType.objects.create(
            operation_type_name=self.operation_type_name1,
            work_type=self.work_type1,
            shop=self.work_type1.shop,
        )
        self.operation_type2 = OperationType.objects.create(
            operation_type_name=self.operation_type_name2,
            work_type=self.work_type2,
            shop=self.work_type2.shop,
        )
        
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='OperationType',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='OperationType',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='DELETE',
            func='OperationType',
            level_up=1,
            level_down=99,
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&work_type_id={self.work_type1.id}')
        self.assertEqual(len(response.json()), 1)
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}')
        self.assertEqual(len(response.json()), 1)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.operation_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'operation_type_name': {
                'id': self.operation_type_name1.id,
                'name': self.operation_type_name1.name,
                'code': self.operation_type_name1.code,
            },
            'shop_id': self.operation_type.shop_id,
            'work_type_id': self.work_type1.id, 
            'do_forecast': OperationType.FORECAST, 
        }
        data['id'] = response.json()['id']
        self.assertEqual(response.json(), data)

    def test_create_with_code(self):
        data = {
            'code': self.operation_type_name3.code,
            'work_type_id': self.work_type3.id, 
            'do_forecast': OperationType.FORECAST,
            'shop_id': self.shop3.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type = response.json()
        data['id'] = operation_type['id']
        data['operation_type_name'] = {
            'id': self.operation_type_name3.id,
            'code': self.operation_type_name3.code,
            'name': self.operation_type_name3.name,
        }
        data.pop('code')
        self.assertEqual(operation_type, data)

    def test_create_with_id(self):
        data = {
            'operation_type_name_id': self.operation_type_name3.id,
            'work_type_id': self.work_type3.id, 
            'do_forecast': OperationType.FORECAST,
            'shop_id': self.shop3.id, 
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type = response.json()
        data['id'] = operation_type['id']
        data['operation_type_name'] = {
            'id': self.operation_type_name3.id,
            'code': self.operation_type_name3.code,
            'name': self.operation_type_name3.name,
        }
        data.pop('operation_type_name_id')
        self.assertEqual(operation_type, data)

    def test_update_by_code(self):
        data = {
            'code': self.operation_type_name3.code,
        }
        response = self.client.put(f'{self.url}{self.operation_type.id}/', data, format='json')
        operation_type = response.json()
        data = {
            'id': self.operation_type.id, 
            'work_type_id': self.work_type1.id, 
            'do_forecast': OperationType.FORECAST,
            'shop_id': self.operation_type.shop_id,
            'operation_type_name': {
                'id': self.operation_type_name3.id,
                'name': self.operation_type_name3.name,
                'code': self.operation_type_name3.code,
            },
        }
        self.assertEqual(operation_type, data)

    def test_update_by_id(self):
        data = {
            'operation_type_name_id': self.operation_type_name3.id,
        }
        response = self.client.put(f'{self.url}{self.operation_type.id}/', data, format='json')
        operation_type = response.json()
        data = {
            'id': self.operation_type.id, 
            'work_type_id': self.work_type1.id, 
            'do_forecast': OperationType.FORECAST,
            'shop_id': self.operation_type.shop_id,
            'operation_type_name': {
                'id': self.operation_type_name3.id,
                'name': self.operation_type_name3.name,
                'code': self.operation_type_name3.code,
            },
        }
        self.assertEqual(operation_type, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.operation_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(OperationType.objects.get(id=self.operation_type.id).dttm_deleted)



    