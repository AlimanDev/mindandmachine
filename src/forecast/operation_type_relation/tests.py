from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.forecast.models import (
    OperationTypeName, 
    OperationType, 
    LoadTemplate, 
    OperationTypeTemplate, 
    OperationTypeRelation,
)
from src.timetable.models import WorkTypeName


class TestOperationTypeRelation(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/operation_type_relation/'

        create_departments_and_users(self)
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=self.network,
        )
        self.work_type_name2 = WorkTypeName.objects.create(
            name='Кассы2',
            network=self.network,
        )
        self.operation_type_name1 = OperationTypeName.objects.create(
            name='Кассы',
            do_forecast=OperationTypeName.FORECAST_FORMULA,
            work_type_name=self.work_type_name1,
            network=self.network,
        )
        self.operation_type_name2 = OperationTypeName.objects.create(
            name='Строительные работы',
            do_forecast=OperationTypeName.FORECAST,
            network=self.network,
        )
        self.operation_type_name3 = OperationTypeName.objects.create(
            name='Строительные работы2',
            work_type_name=self.work_type_name2,
            do_forecast=OperationTypeName.FORECAST_FORMULA,
            network=self.network,
        )

        self.load_template = LoadTemplate.objects.create(
            name='Test1',
            network=self.network,
        )
        self.root_shop.load_template = self.load_template
        self.root_shop.save()
        OperationType.objects.create(
            operation_type_name=self.operation_type_name1,
            shop=self.root_shop,
        )
        self.operation_type_template1 = OperationTypeTemplate.objects.create(
            load_template=self.load_template,
            operation_type_name=self.operation_type_name1,           
        )
        self.operation_type_template2 = OperationTypeTemplate.objects.create(
            load_template=self.load_template,
            operation_type_name=self.operation_type_name2,
        )
        self.operation_type_template3 = OperationTypeTemplate.objects.create(
            load_template=self.load_template,
            operation_type_name=self.operation_type_name3,
        )

        self.operation_type_relation1 = OperationTypeRelation.objects.create(
            base=self.operation_type_template1,
            depended=self.operation_type_template2,
            formula='a * 2',
        )

        self.operation_type_relation2 = OperationTypeRelation.objects.create(
            base=self.operation_type_template3,
            depended=self.operation_type_template2,
            formula='a + 2',
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?base_id={self.operation_type_template1.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 1)
        response = self.client.get(f'{self.url}?depended_id={self.operation_type_template2.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.operation_type_relation1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.operation_type_relation1.id, 
            'base': {
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
            }, 
            'depended': {
                'id': self.operation_type_template2.id, 
                'load_template_id': self.load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name2.id, 
                    'name': 'Строительные работы', 
                    'code': None,
                    'work_type_name_id': None, 
                    'do_forecast': self.operation_type_name2.do_forecast, 
                },
                'tm_from': None,
                'tm_to': None,
                'forecast_step': '01:00:00',
                'const_value': None,
            }, 
            'formula': 'a * 2',
            'type': 'F',
            'max_value': None,
            'threshold': None,
            'days_of_week': [0, 1, 2, 3, 4, 5, 6]
        }
        self.assertEqual(response.json(), data)

    def test_create(self):
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
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type_relataion = response.json()
        data = {
            'id': operation_type_relataion['id'], 
            'base': {
                'id': op_temp1.id, 
                'load_template_id': load_template.id, 
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
            }, 
            'depended': {
                'id': op_temp2.id, 
                'load_template_id': load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name2.id, 
                    'name': 'Строительные работы', 
                    'code': None,
                    'work_type_name_id': None, 
                    'do_forecast': self.operation_type_name2.do_forecast, 
                },
                'tm_from': None,
                'tm_to': None,
                'forecast_step': '01:00:00',
                'const_value': None,
            }, 
            'formula': 'a + a * 2',
            'type': 'F',
            'max_value': None,
            'threshold': None,
            'days_of_week': [0, 1, 2, 3, 4, 5, 6]
        }
        self.assertEqual(operation_type_relataion, data)

    def test_create_change_workload_between(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name3,
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'type': OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
            'max_value': 1.0,
            'threshold': 0.3,
            'days_of_week': [1, 2, 3],
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type_relataion = response.json()
        data = {
            'id': operation_type_relataion['id'], 
            'base': {
                'id': op_temp1.id, 
                'load_template_id': load_template.id, 
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
            }, 
            'depended': {
                'id': op_temp2.id, 
                'load_template_id': load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name3.id, 
                    'name': self.operation_type_name3.name, 
                    'code': None,
                    'work_type_name_id': self.work_type_name2.id, 
                    'do_forecast': self.operation_type_name3.do_forecast, 
                },
                'tm_from': None,
                'tm_to': None,
                'forecast_step': '01:00:00',
                'const_value': None,
            }, 
            'formula': None,
            'type': 'C',
            'max_value': 1.0,
            'threshold': 0.3,
            'days_of_week': [1, 2, 3]
        }
        self.assertEqual(operation_type_relataion, data)
        data = {
            'base_id': op_temp2.id,
            'depended_id': op_temp1.id,
            'type': OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
            'max_value': 1.0,
            'threshold': 0.5,
            'days_of_week': [0, 1, 2, 6],
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_type_relataion = response.json()
        data = {
            'id': operation_type_relataion['id'], 
            'base': {
                'id': op_temp2.id, 
                'load_template_id': load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name3.id, 
                    'name': self.operation_type_name3.name, 
                    'code': None,
                    'work_type_name_id': self.work_type_name2.id, 
                    'do_forecast': self.operation_type_name3.do_forecast, 
                },
                'tm_from': None,
                'tm_to': None,
                'forecast_step': '01:00:00',
                'const_value': None,
            }, 
            'depended': {
                'id': op_temp1.id, 
                'load_template_id': load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name1.id, 
                    'name': self.operation_type_name1.name, 
                    'code': None,
                    'work_type_name_id': self.work_type_name1.id, 
                    'do_forecast': self.operation_type_name1.do_forecast, 
                },
                'tm_from': None,
                'tm_to': None,
                'forecast_step': '01:00:00',
                'const_value': None,
            }, 
            'formula': None,
            'type': 'C',
            'max_value': 1.0,
            'threshold': 0.5,
            'days_of_week': [0, 1, 2, 6]
        }
        self.assertEqual(operation_type_relataion, data)

    def test_create_bad_days_of_week(self):
        self.maxDiff = None
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name3,
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'type': OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
            'max_value': 1.0,
            'threshold': 0.5,
            'days_of_week': [-1, 0, 2],
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'days_of_week': "Некорректное значение дня недели, возможные значения: 0, 1, 2, 3, 4, 5, 6"})
        data['days_of_week'] = [3, 4, 7]
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {'days_of_week': "Некорректное значение дня недели, возможные значения: 0, 1, 2, 3, 4, 5, 6"})

    def test_create_change_workload_between_no_work_type(self):
        self.maxDiff = None
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
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'type': OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
            'max_value': 1.0,
            'threshold': 0.3,
            'days_of_week': [1, 2, 3],
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), ["Оба шаблона должны быть типами работ для взаимосвязи 'Перекидывание типов работ'"])

    def test_update(self):
        data = {
            'formula': 'a * 3',
            'base_id': self.operation_type_template1.id,
            'depended_id': self.operation_type_template2.id,
        }
        self.client.post(
            '/rest_api/load_template/apply/', 
            {
                'id': self.load_template.id,
                'shop_id': self.shop.id,
                'dt_from': None,
            }, 
            format='json',
        )
        OperationType.objects.all().update(status=OperationType.READY)
        response = self.client.put(f'{self.url}{self.operation_type_relation1.id}/', data, format='json')
        operation_type_relation = response.json()
        self.assertEqual(operation_type_relation['formula'], 'a * 3')
        self.assertEqual(
            OperationType.objects.get(operation_type_name=self.operation_type_name1).status,
            OperationType.UPDATED,
        )

    def test_delete(self):
        self.client.post(
            '/rest_api/load_template/apply/', 
            {
                'id': self.load_template.id,
                'shop_id': self.shop.id,
                'dt_from': None,
            }, 
            format='json',
        )
        OperationType.objects.all().update(status=OperationType.READY)
        response = self.client.delete(f'{self.url}{self.operation_type_relation1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            OperationType.objects.get(operation_type_name=self.operation_type_name1).status,
            OperationType.UPDATED,
        )


    def test_bad_steps(self):
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
            forecast_step=timedelta(minutes=30),
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), {'non_field_errors': 'Зависимая операция должна иметь одинаковый или больший шаг прогноза, имеется 0:30:00 -> 1:00:00'})


    def test_bad_formula(self):
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
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'formula': 'a + a ( 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), {'formula': 'Ошибка в формуле: a + a ( 2'})


    def test_base_depended_same(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp1.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), {'non_field_errors': 'Базовая и зависимая модели нагрузки не могут совпадать.'})


    def test_base_not_formula(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        self.operation_type_name1.do_forecast = OperationTypeName.FORECAST
        self.operation_type_name1.save()
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name2,
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), {'base': 'У базовой модели тип расчета должен быть формула'})

    def test_reversed_relation(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        self.operation_type_name2.do_forecast = OperationTypeName.FORECAST_FORMULA
        self.operation_type_name2.save()
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name2,
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        data = {
            'base_id': op_temp2.id,
            'depended_id': op_temp1.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), {'base': 'Уже существует обратная зависимость'})

    def test_cycle_relation(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        self.operation_type_name2.do_forecast = OperationTypeName.FORECAST_FORMULA
        self.operation_type_name2.save()
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name1,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name2,
        )
        op_temp3 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name3,
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        data = {
            'base_id': op_temp2.id,
            'depended_id': op_temp3.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        data = {
            'base_id': op_temp3.id,
            'depended_id': op_temp1.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), {'base': 'Циклическая зависимость: операция зависит сама от себя.'})
