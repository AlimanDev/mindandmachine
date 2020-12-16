from datetime import datetime, timedelta, time
from unittest import skip
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
from src.forecast.load_template.utils import prepare_load_template_request
from src.timetable.models import WorkTypeName, WorkType


class TestLoadTemplate(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/load_template/'

        create_departments_and_users(self)
        self.user1.is_superuser = True
        self.user1.is_staff = True
        self.user1.save()
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
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

        self.load_template = LoadTemplate.objects.create(
            name='Test1',
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

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        LoadTemplate.objects.create(
            name='Test2',
            network=self.network,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.load_template.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.load_template.id, 
            'name': 'Test1', 
            'status': 'R',
            'operation_type_templates': [
                {
                    'id': self.operation_type_template1.id, 
                    'load_template_id': self.load_template.id, 
                    'operation_type_name': {
                        'id': self.operation_type_name1.id, 
                        'name': 'Кассы', 
                        'code': None,
                        'do_forecast': self.operation_type_name1.do_forecast,
                        'work_type_name_id': self.work_type_name1.id, 
                    },
                    'tm_from': None, 
                    'tm_to': None, 
                    'forecast_step': '01:00:00',
                    'const_value': None,
                }, 
                {
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
                }
            ]
        }
        self.assertEqual(response.json(), data)

    def test_create(self):
        data = {
            'name': 'Тестовый шаблон',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        load_template = response.json()
        data['id'] = load_template['id']
        data['operation_type_templates'] = []
        self.assertEqual(load_template, data)

    def test_update(self):
        data = {
            'name': 'Test2',
        }
        response = self.client.put(f'{self.url}{self.load_template.id}/', data, format='json')
        load_template = response.json()
        data['id'] = self.load_template.id
        data['status'] = 'R'
        data['operation_type_templates'] = [
            {
                'id': self.operation_type_template1.id, 
                'load_template_id': self.load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name1.id, 
                    'name': 'Кассы', 
                    'code': None,
                    'do_forecast': self.operation_type_name1.do_forecast,
                    'work_type_name_id': self.work_type_name1.id, 
                },
                'tm_from': None, 
                'tm_to': None, 
                'forecast_step': '01:00:00',
                'const_value': None,
            }, 
            {
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
            }
        ]
        self.assertEqual(load_template, data)

    def test_apply_template(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            data = {
                'id': self.load_template.id,
                'shop_id': self.shop.id,
            }
            response = self.client.post(f'{self.url}apply/', data, format='json')
            self.assertEqual(response.status_code, 200)

            self.assertEqual(OperationType.objects.filter(shop=self.shop).count(), 2)
            self.assertEqual(WorkType.objects.filter(shop=self.shop).count(), 1)


    def test_prepare_load_template_request(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            OperationTypeRelation.objects.create(
                base=self.operation_type_template1,
                depended=self.operation_type_template2,
                formula='lambda a: a * 2 + a',
            )
            dt_now = datetime.now().date()
            data = {
                'id': self.load_template.id,
                'shop_id': self.shop.id,
                'dt_from': dt_now,
                'dt_to': dt_now + timedelta(days=1)
            }
            self.client.post(f'{self.url}apply/', data, format='json')

            operation_type = OperationType.objects.get(shop=self.shop, operation_type_name=self.operation_type_name2)

            for day in range(2):
                dt = dt_now + timedelta(days=day)
                for tm in range(24):
                    PeriodClients.objects.create(
                        dttm_forecast=datetime.combine(dt, time(tm)),
                        value=2.0,
                        operation_type=operation_type,
                        type=PeriodClients.FACT_TYPE,
                    )
            request = prepare_load_template_request(self.load_template.id, self.shop.id, dt_from=dt_now, dt_to=dt_now + timedelta(days=1))
            self.assertEqual(len(request['timeserie'][str(self.operation_type_name2.id)]), 48)
            self.assertEqual(len(request['operation_types']), 2)
            self.assertEqual(len(request['operation_types'][0]['dependences']), 1)
            self.assertEqual(len(request['operation_types'][1]['dependences']), 0)            

    @skip('А нужен ли этот функционал?')
    def test_create_from_shop(self):
        data = {
            'name': 'Тестовый шаблон',
            'shop_id': self.shop.id,
        }
        OperationType.objects.create(
            shop=self.shop,
            operation_type_name=self.operation_type_name1,
            do_forecast=OperationType.FORECAST_FORMULA,
            work_type=WorkType.objects.create(
                work_type_name=self.work_type_name1,
                shop=self.shop,
            ),
        )
        OperationType.objects.create(
            shop=self.shop,
            operation_type_name=self.operation_type_name2,
            do_forecast=OperationType.FORECAST_NONE,
        )
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        load_template = response.json()
        data = {
            'id': load_template['id'], 
            'name': 'Шаблон нагрузки для магазина Shop1', 
            'status': 'R',
            'operation_type_templates': [
                {
                    'id': load_template['operation_type_templates'][0]['id'], 
                    'load_template_id': load_template['id'], 
                    'work_type_name_id': self.work_type_name1.id, 
                    'operation_type_name': {
                        'id': self.operation_type_name1.id, 
                        'name': 'Кассы', 
                        'code': None,
                        'do_corecast': 'F',
                        'work_type_name_id': None
                    }
                }, 
                {
                    'id': load_template['operation_type_templates'][1]['id'], 
                    'load_template_id': load_template['id'], 
                    'work_type_name_id': None, 
                    'do_forecast': 'N', 
                    'operation_type_name': {
                        'id': self.operation_type_name2.id, 
                        'name': 'Строительные работы', 
                        'code': None
                    }
                }
            ]
        }
        self.assertEqual(load_template, data)
    

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.load_template.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    
    def test_apply_template_to_shop_on_load_template_change(self):
        self.assertEqual(OperationType.objects.filter(shop=self.shop).count(), 0)
        self.assertEqual(WorkType.objects.filter(shop=self.shop).count(), 0)
        self.shop.load_template = self.load_template
        self.shop.save()
        self.assertEqual(OperationType.objects.filter(shop=self.shop).count(), 2)
        self.assertEqual(WorkType.objects.filter(shop=self.shop).count(), 1)
