from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase
from src.util.mixins.tests import TestsHelperMixin

from src.forecast.models import (
    OperationTypeName, 
    OperationType, 
    LoadTemplate, 
    OperationTypeTemplate, 
    OperationTypeRelation,
)
from src.timetable.models import WorkTypeName


class TestOperationTypeRelation(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/operation_type_relation/'

        cls.create_departments_and_users()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )
        cls.work_type_name2 = WorkTypeName.objects.create(
            name='Кассы2',
            network=cls.network,
        )
        cls.operation_type_name1 = cls.work_type_name1.operation_type_name
        cls.operation_type_name2 = OperationTypeName.objects.create(
            name='Строительные работы',
            do_forecast=OperationTypeName.FORECAST,
            network=cls.network,
        )
        cls.operation_type_name3 = cls.work_type_name2.operation_type_name
        cls.operation_type_name4 = OperationTypeName.objects.create(
            name='Продажи',
            do_forecast=OperationTypeName.FORECAST,
            network=cls.network,
        )

        cls.load_template = LoadTemplate.objects.create(
            name='Test1',
            network=cls.network,
        )
        cls.root_shop.load_template = cls.load_template
        cls.root_shop.save()
        OperationType.objects.create(
            operation_type_name=cls.operation_type_name1,
            shop=cls.root_shop,
        )
        cls.operation_type_template1 = OperationTypeTemplate.objects.create(
            load_template=cls.load_template,
            operation_type_name=cls.operation_type_name1,           
        )
        cls.operation_type_template2 = OperationTypeTemplate.objects.create(
            load_template=cls.load_template,
            operation_type_name=cls.operation_type_name2,
        )
        cls.operation_type_template3 = OperationTypeTemplate.objects.create(
            load_template=cls.load_template,
            operation_type_name=cls.operation_type_name3,
        )

        cls.operation_type_relation1 = OperationTypeRelation.objects.create(
            base=cls.operation_type_template1,
            depended=cls.operation_type_template2,
            formula='a * 2',
        )
        cls.operation_type_relation2 = OperationTypeRelation.objects.create(
            base=cls.operation_type_template3,
            depended=cls.operation_type_template2,
            formula='a + 2',
        )

    def setUp(self):
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
            'days_of_week': [],
            'order': None,
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
            'days_of_week': [0, 1, 2, 3, 4, 5, 6],
            'order': None,
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
            'days_of_week': [1, 2, 3],
            'order': 999,
        }
        self.assertEqual(operation_type_relataion, data)
        data = {
            'base_id': op_temp2.id,
            'depended_id': op_temp1.id,
            'type': OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
            'max_value': 1.0,
            'threshold': 0.5,
            'days_of_week': [0, 1, 2, 6],
            'order': 1,
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
            'days_of_week': [0, 1, 2, 6],
            'order': 1,
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
            'days_of_week': [-1, 0, 2, 7],
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['days_of_week'], [0, 2])

    def test_create_formula_no_formula(self):
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
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), ["Формула обязательна в отношении Кассы -> Строительные работы"])

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
        self.assertEqual(response.json(), ['Зависимая операция должна иметь одинаковый или больший шаг прогноза, имеется 0:30:00 -> 1:00:00'])


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
            'formula': 'a + a , 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), ['Ошибка в формуле: a + a , 2'])


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
        self.assertEqual(response.json(), ['Базовая и зависимая модели нагрузки не могут совпадать.'])


    def test_base_forecast_depended_formula(self):
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
            'base_id': op_temp2.id,
            'depended_id': op_temp1.id,
            'formula': 'a + a * 2'
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), ['Прогнозируемый тип Строительные работы не может зависеть от Кассы с типом расчета по формуле.'])

    def test_reversed_relation(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name2,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name4,
        )
        data = {
            'base_id': op_temp1.id,
            'depended_id': op_temp2.id,
        }
        response = self.client.post(self.url, data, format='json')
        data = {
            'base_id': op_temp2.id,
            'depended_id': op_temp1.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.json(), ['Уже существует обратная зависимость'])

    def test_cycle_relation(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        self.operation_type_name2.do_forecast = OperationTypeName.FORECAST_FORMULA
        self.operation_type_name2.save()
        self.operation_type_name4.do_forecast = OperationTypeName.FORECAST_FORMULA
        self.operation_type_name4.save()
        self.operation_type_name5 = OperationTypeName.objects.create(
            name='Входящие',
            do_forecast=OperationTypeName.FORECAST_FORMULA,
            network=self.network,
        )
        op_temp1 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name2,
        )
        op_temp2 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name4,
        )
        op_temp3 = OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name=self.operation_type_name5,
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
        self.assertEqual(response.json(), ['Циклическая зависимость: операция зависит сама от себя.'])

    def _test_relation_type(self, base, depended, type, formula=None, max_value=None, order=None, threshold=None, days_of_week=[]):
        op_rel = OperationTypeRelation.objects.create(
            base=base,
            depended=depended,
            formula=formula,
            max_value=max_value,
            order=order,
            threshold=threshold,
            days_of_week=days_of_week,
        )
        self.assertEqual(op_rel.type, type)
        self.assertEqual(op_rel.formula, formula)
        self.assertEqual(op_rel.max_value, max_value)
        self.assertEqual(op_rel.order, order)
        self.assertEqual(op_rel.threshold, threshold)
        self.assertEqual(op_rel.days_of_week_list, days_of_week)
        op_rel.delete()

    def test_create_type(self):
        load_template = LoadTemplate.objects.create(
            name='TEST'
        )
        operation_type1 = OperationTypeName.objects.create(
            name='Formula 1',
            do_forecast=OperationTypeName.FORECAST_FORMULA,
        )
        operation_type2 = OperationTypeName.objects.create(
            name='Formula 2',
            do_forecast=OperationTypeName.FORECAST_FORMULA,
        )
        feature_serie_name = OperationTypeName.objects.create(
            name='Feature serie',
            do_forecast=OperationTypeName.FEATURE_SERIE,
        )
        def _create_operation_type_template(o_name):
            return OperationTypeTemplate.objects.create(
                load_template=load_template,
                operation_type_name=o_name,
            )
        work_type_operation1 = _create_operation_type_template(self.operation_type_name1)
        work_type_operation2 = _create_operation_type_template(self.operation_type_name3)
        forecast_operation1 = _create_operation_type_template(self.operation_type_name2)
        forecast_operation2 = _create_operation_type_template(self.operation_type_name4)
        formula_operation1 = _create_operation_type_template(operation_type1)
        formula_operation2 = _create_operation_type_template(operation_type2)
        feature_serie = _create_operation_type_template(feature_serie_name)

        # predict relation

        self._test_relation_type(forecast_operation1, forecast_operation2, OperationTypeRelation.TYPE_PREDICTION)
        self._test_relation_type(forecast_operation1, feature_serie, OperationTypeRelation.TYPE_PREDICTION)
        
        # formula relation

        self._test_relation_type(formula_operation1, forecast_operation2, OperationTypeRelation.TYPE_FORMULA, formula='a')
        self._test_relation_type(formula_operation1, formula_operation2, OperationTypeRelation.TYPE_FORMULA, formula='a')
        self._test_relation_type(work_type_operation1, formula_operation2, OperationTypeRelation.TYPE_FORMULA, formula='a')
        self._test_relation_type(work_type_operation1, forecast_operation1, OperationTypeRelation.TYPE_FORMULA, formula='a')

        # change worload between relation
        self._test_relation_type(
            work_type_operation1, 
            work_type_operation2, 
            OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
            max_value=1,
            threshold=0.2,
            order=1,
            days_of_week=[1, 2, 4],
        )

