from datetime import datetime, timedelta, time

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.forecast.models import (
    OperationTypeName, 
    OperationType, 
    LoadTemplate, 
    OperationTypeTemplate, 
    OperationTypeRelation,
    PeriodClients,
)
from src.timetable.models import WorkTypeName, WorkType
from src.base.models import FunctionGroup


class TestOperationTypeTemplate(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/operation_type_template/'

        create_departments_and_users(self)
        self.user1.is_superuser = True
        self.user1.is_staff = True
        self.user1.save()
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=self.network,
        )

        self.load_template = LoadTemplate.objects.create(
            name='Test1',
            network=self.network,
        )
        self.operation_type_name1 = OperationTypeName.objects.create(
            name='Кассы',
            work_type_name=self.work_type_name1,
            do_forecast=OperationTypeName.FORECAST_FORMULA,
            network=self.network,
        )
        self.operation_type_name2 = OperationTypeName.objects.create(
            name='Строительные работы',
            do_forecast=OperationTypeName.FORECAST,
            network=self.network,
        )
        self.operation_type_name3 = OperationTypeName.objects.create(
            name='Строительные работы2',
            network=self.network,
        )
        
        self.operation_type_template1 = OperationTypeTemplate.objects.create(
            load_template=self.load_template,
            operation_type_name=self.operation_type_name1,
        )
        self.operation_type_template2 = OperationTypeTemplate.objects.create(
            load_template=self.load_template,
            operation_type_name=self.operation_type_name2,
        )
        FunctionGroup.objects.bulk_create(
            [
                FunctionGroup(func='OperationTypeTemplate', group=self.admin_group, method=m)
                for m in ['POST', 'PUT', 'DELETE']
            ]
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.operation_type_template1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.operation_type_template1.id, 
            'load_template_id': self.load_template.id, 
            'operation_type_name': {
                'id': self.operation_type_name1.id, 
                'name': 'Кассы', 
                'code': None,
                'work_type_name_id': self.work_type_name1.id, 
                'do_forecast': self.operation_type_name1.do_forecast, 
            },
            'tm_from': None,
            'tm_to': None,
            'forecast_step': '01:00:00'
        }
        self.assertEqual(response.json(), data)

    def test_create(self):
        data = {
            'load_template_id': self.load_template.id,
            'operation_type_name_id': self.operation_type_name3.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type_template = response.json()
        data = {
            'id': operation_type_template['id'], 
            'load_template_id': self.load_template.id, 
            'operation_type_name': {
                'id': self.operation_type_name3.id, 
                'name': 'Строительные работы2', 
                'code': None,
                'work_type_name_id': None, 
                'do_forecast': self.operation_type_name3.do_forecast, 
            },
            'tm_from': None,
            'tm_to': None,
            'forecast_step': '01:00:00'
        }
        self.assertEqual(operation_type_template, data)

    def test_update(self):
        data = {
            'load_template_id': self.load_template.id,
            'operation_type_name_id': self.operation_type_name1.id,
            'forecast_step': '00:30:00'
        }
        response = self.client.put(f'{self.url}{self.operation_type_template1.id}/', data, format='json')
        operation_type_template = response.json()
        data = {
            'id': self.operation_type_template1.id, 
            'load_template_id': self.load_template.id, 
            'operation_type_name': {
                'id': self.operation_type_name1.id, 
                'name': 'Кассы', 
                'code': None,
                'work_type_name_id': self.work_type_name1.id, 
                'do_forecast': self.operation_type_name1.do_forecast, 
            },
            'tm_from': None,
            'tm_to': None,
            'forecast_step': '00:30:00'
        }
        self.assertEqual(operation_type_template, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.operation_type_template1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    