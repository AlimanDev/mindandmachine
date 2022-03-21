from unittest.case import skip

from rest_framework import status
from rest_framework.test import APITestCase
from src.util.mixins.tests import TestsHelperMixin

from src.forecast.models import OperationTypeName, OperationType
from src.timetable.models import WorkTypeName, WorkType


class TestOperationType(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/operation_type/'

        cls.create_departments_and_users()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.work_type2 = WorkType.objects.create(shop=cls.shop2, work_type_name=cls.work_type_name1)
        cls.work_type3 = WorkType.objects.create(shop=cls.shop3, work_type_name=cls.work_type_name1)

        cls.operation_type_name1 = cls.work_type_name1.operation_type_name
        cls.operation_type_name2 = OperationTypeName.objects.create(
            name='продажа2',
            code='2',
            network=cls.network,
        )

        cls.operation_type = cls.work_type1.operation_type
        cls.operation_type2 = cls.work_type2.operation_type

    def setUp(self):
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
                'do_forecast': OperationTypeName.FORECAST_FORMULA, 
                'work_type_name_id': self.operation_type_name1.work_type_name_id,
            },
            'shop_id': self.operation_type.shop_id,
            'work_type_id': self.work_type1.id, 
        }
        data['id'] = response.json()['id']
        self.assertEqual(response.json(), data)

    def test_create_with_code(self):
        data = {
            'code': self.operation_type_name2.code,
            'work_type_id': None, # read only 
            'shop_id': self.shop3.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type = response.json()
        data['id'] = operation_type['id']
        data['operation_type_name'] = {
            'id': self.operation_type_name2.id,
            'code': self.operation_type_name2.code,
            'name': self.operation_type_name2.name,
            'do_forecast': self.operation_type_name2.do_forecast,
            'work_type_name_id': self.operation_type_name2.work_type_name_id,
        }
        data.pop('code')
        self.assertEqual(operation_type, data)

    def test_create_with_id(self):
        data = {
            'operation_type_name_id': self.operation_type_name2.id,
            'work_type_id': None, # read only
            'shop_id': self.shop3.id, 
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type = response.json()
        data['id'] = operation_type['id']
        data['operation_type_name'] = {
            'id': self.operation_type_name2.id,
            'code': self.operation_type_name2.code,
            'name': self.operation_type_name2.name,
            'do_forecast': self.operation_type_name2.do_forecast,
            'work_type_name_id': self.operation_type_name2.work_type_name_id,
        }
        data.pop('operation_type_name_id')
        self.assertEqual(operation_type, data)

    @skip('Пока не используем')
    def test_update_by_code(self):
        data = {
            'code': self.operation_type_name2.code,
        }
        response = self.client.put(f'{self.url}{self.operation_type.id}/', data, format='json')
        operation_type = response.json()
        data = {
            'id': self.operation_type.id, 
            'work_type_id': self.work_type1.id, 
            'shop_id': self.operation_type.shop_id,
            'operation_type_name': {
                'id': self.operation_type_name3.id,
                'name': self.operation_type_name3.name,
                'code': self.operation_type_name3.code,
                'do_forecast': self.operation_type_name3.do_forecast,
                'work_type_name_id': self.operation_type_name3.work_type_name_id,
            },
        }
        self.assertEqual(operation_type, data)

    @skip('Пока не используем')
    def test_update_by_id(self):
        data = {
            'operation_type_name_id': self.operation_type_name2.id,
        }
        response = self.client.put(f'{self.url}{self.operation_type.id}/', data, format='json')
        operation_type = response.json()
        data = {
            'id': self.operation_type.id, 
            'work_type_id': self.work_type1.id, 
            'shop_id': self.operation_type.shop_id,
            'operation_type_name': {
                'id': self.operation_type_name3.id,
                'name': self.operation_type_name3.name,
                'code': self.operation_type_name3.code,
                'do_forecast': self.operation_type_name3.do_forecast,
                'work_type_name_id': self.operation_type_name3.work_type_name_id,
            },
        }
        self.assertEqual(operation_type, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.operation_type.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(OperationType.objects.get(id=self.operation_type.id).dttm_deleted)



    