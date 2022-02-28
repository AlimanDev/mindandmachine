from rest_framework import status
from rest_framework.test import APITestCase
from src.util.mixins.tests import TestsHelperMixin


from src.forecast.models import OperationTypeName, OperationType
from src.timetable.models import WorkTypeName, WorkType


class TestOperationTypeName(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/operation_type_name/'

        cls.create_departments_and_users()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )
        cls.operation_type_name1 = cls.work_type_name1.operation_type_name
        cls.work_type = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.operation_type_name2 = OperationTypeName.objects.create(
            name='Тип_кассы_2',
            network=cls.network,
        )
        cls.operation_type_name3 = OperationTypeName.objects.create(
            name='Тип_кассы_3',
            network=cls.network,
        )
        cls.operation_type_name4 = OperationTypeName.objects.create(
            name='тип_кассы_4',
            network=cls.network,
        )


    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 4)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.operation_type_name1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {'name': 'Кассы', 'code': None}
        data['id'] = response.json()['id']
        data['do_forecast'] = OperationTypeName.FORECAST_FORMULA
        data['work_type_name_id'] = self.work_type_name1.id
        self.assertEqual(response.json(), data)

    def test_create(self):
        data = {
            'name': 'Отдел электроники',
            'code': '23',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type_name = response.json()
        data['id'] = operation_type_name['id']
        data['do_forecast'] = OperationTypeName.FORECAST
        data['work_type_name_id'] = None
        self.assertEqual(operation_type_name, data)

    def test_update(self):
        data = {
            'name': 'Склад',
            'code': '21',
        }
        response = self.client.put(f'{self.url}{self.operation_type_name2.id}/', data, format='json')
        operation_type_name = response.json()
        data['id'] = self.operation_type_name2.id
        data['do_forecast'] = OperationTypeName.FORECAST
        data['work_type_name_id'] = None
        self.assertEqual(operation_type_name, data)

    def test_update_name(self):
        data = {
            'name': 'Склад',
        }
        response = self.client.put(f'{self.url}{self.operation_type_name2.id}/', data, format='json')
        operation_type_name = response.json()
        data['id'] = self.operation_type_name2.id
        data['code'] = self.operation_type_name2.code
        data['do_forecast'] = OperationTypeName.FORECAST
        data['work_type_name_id'] = None
        self.assertEqual(operation_type_name, data)

    def test_update_code(self):
        data = {
            'code': '21',
        }
        response = self.client.put(f'{self.url}{self.operation_type_name2.id}/', data, format='json')
        operation_type_name = response.json()
        data['id'] = self.operation_type_name2.id
        data['name'] = self.operation_type_name2.name
        data['do_forecast'] = OperationTypeName.FORECAST
        data['work_type_name_id'] = None
        self.assertEqual(operation_type_name, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.operation_type_name1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(OperationTypeName.objects.get(id=self.operation_type_name1.id).dttm_deleted)
        self.assertEqual(OperationType.objects.filter(dttm_deleted__isnull=False).count(), 1)


    