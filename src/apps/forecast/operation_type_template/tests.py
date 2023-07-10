from rest_framework import status
from rest_framework.test import APITestCase
from src.common.mixins.tests import TestsHelperMixin


from src.apps.forecast.models import (
    OperationTypeName, 
    LoadTemplate, 
    OperationTypeTemplate, 
    OperationTypeRelation,
)
from src.apps.timetable.models import WorkTypeName


class TestOperationTypeTemplate(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/operation_type_template/'

        cls.create_departments_and_users()
        cls.user1.is_superuser = True
        cls.user1.is_staff = True
        cls.user1.save()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )

        cls.load_template = LoadTemplate.objects.create(
            name='Test1',
            network=cls.network,
        )
        cls.operation_type_name1 = cls.work_type_name1.operation_type_name
        cls.operation_type_name2 = OperationTypeName.objects.create(
            name='Строительные работы',
            do_forecast=OperationTypeName.FORECAST,
            network=cls.network,
        )
        cls.operation_type_name3 = OperationTypeName.objects.create(
            name='Строительные работы2',
            network=cls.network,
        )
        
        cls.operation_type_template1 = OperationTypeTemplate.objects.create(
            load_template=cls.load_template,
            operation_type_name=cls.operation_type_name1,
        )
        cls.operation_type_template2 = OperationTypeTemplate.objects.create(
            load_template=cls.load_template,
            operation_type_name=cls.operation_type_name2,
        )

    def setUp(self):
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
            'forecast_step': '01:00:00',
            'const_value': None,
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
            'forecast_step': '01:00:00',
            'const_value': None,
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
            'forecast_step': '00:30:00',
            'const_value': None,
        }
        self.assertEqual(operation_type_template, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.operation_type_template1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    

    def test_cant_change_forecast_step(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name2,
        )
        OperationTypeRelation.objects.create(
            base=op_temp1,
            depended=op_temp2,
            formula='a * 2 + a',
        )
        data = {
            'load_template_id': load_template.id,
            'operation_type_name_id': self.operation_type_name1.id,
            'forecast_step': '1 00:00:00'
        }
        response = self.client.put(f'{self.url}{op_temp1.id}/', data, format='json')
        self.assertEqual(response.json(), {'non_field_errors': 'Этот тип операции зависит от операций с меньшим шагом прогноза.'})
        data = {
            'load_template_id': load_template.id,
            'operation_type_name_id': self.operation_type_name2.id,
            'forecast_step': '00:30:00'
        }
        response = self.client.put(f'{self.url}{op_temp2.id}/', data, format='json')
        self.assertEqual(response.json(), {'non_field_errors': 'От этого типа операций зависят операции с большим шагом прогноза.'})


    def test_cant_set_const(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name2,
        )
        OperationTypeRelation.objects.create(
            base=op_temp1,
            depended=op_temp2,
            formula='a * 2 + a',
        )
        data = {
            'load_template_id': load_template.id,
            'operation_type_name_id': self.operation_type_name1.id,
            'const_value': 1.0,
        }
        response = self.client.put(f'{self.url}{op_temp1.id}/', data, format='json')
        self.assertEqual(response.json(), {'non_field_errors': 'Вы не можете указать постоянное значение, так как у данной операции есть зависимости.'})
