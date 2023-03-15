from datetime import datetime, timedelta, time
from io import BytesIO
from unittest import skip
from rest_framework import status
from rest_framework.test import APITestCase
import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from src.util.mixins.tests import TestsHelperMixin

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


class TestLoadTemplate(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/load_template/'

        cls.create_departments_and_users()
        cls.user1.is_superuser = True
        cls.user1.is_staff = True
        cls.user1.save()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )
        cls.operation_type_name1 = cls.work_type_name1.operation_type_name
        cls.operation_type_name2 = OperationTypeName.objects.create(
            name='Строительные работы',
            do_forecast=OperationTypeName.FORECAST,
            network=cls.network,
        )
        cls.work_type_name2 = WorkTypeName.objects.create(
            name='ДМ',
            network=cls.network,
        )
        cls.operation_type_name3 = cls.work_type_name2.operation_type_name
        cls.operation_type_name4 = OperationTypeName.objects.create(
            name='Продажи',
            do_forecast=OperationTypeName.FEATURE_SERIE,
            network=cls.network,
        )
        cls.operation_type_name5 = OperationTypeName.objects.create(
            name='Входящие',
            do_forecast=OperationTypeName.FORECAST,
            network=cls.network,
        )
        cls.operation_type_name6 = OperationTypeName.objects.create(
            name='Пробитие чека',
            do_forecast=OperationTypeName.FORECAST_FORMULA,
            network=cls.network,
        )

        cls.load_template = LoadTemplate.objects.create(
            name='Test1',
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
        cls.operation_type_template3 = OperationTypeTemplate.objects.create(
            load_template=cls.load_template,
            operation_type_name=cls.operation_type_name3,
        )
        cls.operation_type_template4 = OperationTypeTemplate.objects.create(
            load_template=cls.load_template,
            operation_type_name=cls.operation_type_name4,
        )

    def setUp(self):
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
            'round_delta': 0.0,
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
                },
                {
                    'id': self.operation_type_template3.id, 
                    'load_template_id': self.load_template.id, 
                    'operation_type_name': {
                        'id': self.operation_type_name3.id, 
                        'name': 'ДМ', 
                        'code': None,
                        'do_forecast': self.operation_type_name3.do_forecast,
                        'work_type_name_id': self.work_type_name2.id, 
                    },
                    'tm_from': None, 
                    'tm_to': None, 
                    'forecast_step': '01:00:00',
                    'const_value': None,
                },
                {
                    'id': self.operation_type_template4.id, 
                    'load_template_id': self.load_template.id, 
                    'operation_type_name': {
                        'id': self.operation_type_name4.id, 
                        'name': self.operation_type_name4.name, 
                        'code': None,
                        'do_forecast': self.operation_type_name4.do_forecast,
                        'work_type_name_id': None, 
                    },
                    'tm_from': None, 
                    'tm_to': None, 
                    'forecast_step': '01:00:00',
                    'const_value': None,
                }, 
            ]
        }
        self.assertEqual(response.json(), data)

    def test_create(self):
        data = {
            'name': 'Тестовый шаблон',
            'round_delta': 0.8,
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
            'round_delta': 0.5,
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
            },
            {
                'id': self.operation_type_template3.id, 
                'load_template_id': self.load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name3.id, 
                    'name': 'ДМ', 
                    'code': None,
                    'do_forecast': self.operation_type_name3.do_forecast,
                    'work_type_name_id': self.work_type_name2.id, 
                },
                'tm_from': None, 
                'tm_to': None, 
                'forecast_step': '01:00:00',
                'const_value': None,
            }, 
            {
                'id': self.operation_type_template4.id, 
                'load_template_id': self.load_template.id, 
                'operation_type_name': {
                    'id': self.operation_type_name4.id, 
                    'name': self.operation_type_name4.name, 
                    'code': None,
                    'do_forecast': self.operation_type_name4.do_forecast,
                    'work_type_name_id': None, 
                },
                'tm_from': None, 
                'tm_to': None, 
                'forecast_step': '01:00:00',
                'const_value': None,
            },
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

            self.assertEqual(OperationType.objects.filter(shop=self.shop).count(), 4)
            self.assertEqual(WorkType.objects.filter(shop=self.shop, dttm_deleted__isnull=True).count(), 2)
            WorkType.objects.filter(shop=self.shop).update(dttm_deleted=datetime.now())
            self.assertEqual(WorkType.objects.filter(shop=self.shop, dttm_deleted__isnull=True).count(), 0)
            response = self.client.post(f'{self.url}apply/', data, format='json')
            self.assertEqual(WorkType.objects.filter(shop=self.shop, dttm_deleted__isnull=True).count(), 2)


    def test_prepare_load_template_request(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            OperationTypeRelation.objects.create(
                base=self.operation_type_template2,
                depended=self.operation_type_template4,
                type=OperationTypeRelation.TYPE_PREDICTION,
            )
            OperationTypeRelation.objects.create(
                base=self.operation_type_template1,
                depended=self.operation_type_template2,
                formula='a * 2 + a',
            )
            OperationTypeRelation.objects.create(
                base=self.operation_type_template1,
                depended=self.operation_type_template3,
                max_value=1.0,
                threshold=0.4,
                days_of_week=[1, 2, 4],
                order=1,
                type=OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
            )
            dt_now = datetime.now().date()
            data = {
                'id': self.load_template.id,
                'shop_id': self.shop.id,
                'dt_from': dt_now,
                'dt_to': dt_now + timedelta(days=1)
            }
            self.client.post(f'{self.url}apply/', data, format='json')
            self.shop.refresh_from_db()
            self.shop.load_template_settings = '{"reserve_coef": 0.2}'
            self.shop.save()
            self.shop.load_template_status = 'R'
            self.shop.save()

            operation_type = OperationType.objects.get(shop=self.shop, operation_type_name=self.operation_type_name2)
            operation_type2 = OperationType.objects.get(shop=self.shop, operation_type_name=self.operation_type_name4)
            for ot in [operation_type, operation_type2]:
                for day in range(2):
                    dt = dt_now + timedelta(days=day)
                    for tm in range(24):
                        PeriodClients.objects.create(
                            dttm_forecast=datetime.combine(dt, time(tm)),
                            dt_report=dt,
                            value=2.0,
                            operation_type=ot,
                            type=PeriodClients.FACT_TYPE,
                        )
            request = prepare_load_template_request(self.load_template.id, self.shop.id, dt_from=dt_now, dt_to=dt_now + timedelta(days=1))
            self.assertEqual(request['shop']['reserve_coef'], 0.2)
            self.assertEqual(len(request['timeserie'][str(self.operation_type_name2.id)]), 48)
            self.assertEqual(len(request['timeserie'][str(self.operation_type_name4.id)]), 48)
            self.assertEqual(len(request['operation_types']), 4)
            self.assertEqual(len(request['operation_types'][0]['dependences']), 1)
            self.assertEqual(request['operation_types'][0]['type'], 'O')
            self.assertEqual(len(request['operation_types'][1]['dependences']), 1)            
            self.assertEqual(request['operation_types'][1]['type'], 'F')            
            self.assertEqual(len(request['operation_types'][3]['dependences']), 0)            
            self.assertEqual(request['operation_types'][3]['type'], 'FS')            
            self.assertEqual(len(request['change_workload_between']), 1)            
            self.assertEqual(
                request['change_workload_between'][0], 
                {
                    'to_serie': self.operation_type_name1.id, 
                    'from_serie': self.operation_type_name3.id, 
                    'threshold': 0.4, 
                    'max_value': 1.0, 
                    'days_of_week': [1, 2, 4],
                    'order': 1,
                }
            )            


    def test_prepare_load_template_request_shop_in_progress(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            OperationTypeRelation.objects.create(
                base=self.operation_type_template1,
                depended=self.operation_type_template2,
                formula='a * 2 + a',
            )
            dt_now = datetime.now().date()
            self.shop.load_template = self.load_template
            self.shop.save()
            self.shop.load_template_status = self.shop.LOAD_TEMPLATE_PROCESS
            self.shop.save()

            operation_type = OperationType.objects.get(shop=self.shop, operation_type_name=self.operation_type_name2)

            for day in range(2):
                dt = dt_now + timedelta(days=day)
                for tm in range(24):
                    PeriodClients.objects.create(
                        dttm_forecast=datetime.combine(dt, time(tm)),
                        dt_report=dt,
                        value=2.0,
                        operation_type=operation_type,
                        type=PeriodClients.FACT_TYPE,
                    )
            request = prepare_load_template_request(self.load_template.id, self.shop.id, dt_from=dt_now, dt_to=dt_now + timedelta(days=1))
            self.assertIsNone(request)


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
        self.assertEqual(OperationType.objects.filter(shop=self.shop).count(), 4)
        self.assertEqual(WorkType.objects.filter(shop=self.shop).count(), 2)

    def test_download_upload(self):
        OperationTypeRelation.objects.create(
            base=self.operation_type_template2,
            depended=self.operation_type_template4,
            type=OperationTypeRelation.TYPE_PREDICTION,
        )
        OperationTypeRelation.objects.create(
            base=self.operation_type_template1,
            depended=self.operation_type_template2,
            formula='a * 2 + a',
        )
        OperationTypeRelation.objects.create(
            base=self.operation_type_template1,
            depended=self.operation_type_template3,
            max_value=1.0,
            threshold=0.4,
            days_of_week=[1, 2, 4],
            order=1,
            type=OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
        )
        response = self.client.get(f'/rest_api/load_template/{self.load_template.id}/download/')
        
        df = pd.read_excel(response.content).fillna('')
        data = [
            {
                'Тип операции': 'Продажи', 
                'Зависимости': '', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '', 
            }, 
            {
                'Тип операции': 'Строительные работы', 
                'Зависимости': 'Продажи', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '', 
            }, 
            {
                'Тип операции': 'Кассы', 
                'Зависимости': 'Строительные работы', 
                'Формула': 'a * 2 + a', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '',
            }, 
            {
                'Тип операции': '', 
                'Зависимости': 'ДМ', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': 1.0, 
                'Порог': 0.4, 
                'Порядок': 1.0,
                'Дни недели (через запятую)': '1,2,4', 
                'Шаг прогноза': '', 
                'Время начала': '', 
                'Время окончания': '', 
            }, 
            {
                'Тип операции': 'ДМ', 
                'Зависимости': '', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '', 
            }
        ]
        self.assertEqual(df.to_dict('records'), data)
        response = self.client.post(
            '/rest_api/load_template/upload/',
            {
                'name': 'Test2',
                'file': SimpleUploadedFile('template.xlsx', response.content)
            }
        )
        self.assertEqual(response.status_code, 200)
        lt = LoadTemplate.objects.get(name='Test2')
        self.assertEquals(OperationTypeTemplate.objects.filter(load_template=lt).count(), 4)
        self.assertEquals(OperationTypeRelation.objects.filter(base__load_template=lt).count(), 3)
        formula_relation = OperationTypeRelation.objects.get(base__load_template=lt, type=OperationTypeRelation.TYPE_FORMULA)
        self.assertEquals(formula_relation.formula, 'a * 2 + a')
        self.assertEquals(formula_relation.days_of_week_list, [])
        self.assertEquals(formula_relation.base.operation_type_name_id, self.operation_type_name1.id)
        self.assertEquals(formula_relation.depended.operation_type_name_id, self.operation_type_name2.id)
        self.assertEquals(formula_relation.max_value, None)
        self.assertEquals(formula_relation.threshold, None)
        change_workload_relation = OperationTypeRelation.objects.get(base__load_template=lt, type=OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN)
        self.assertEquals(change_workload_relation.formula, '')
        self.assertEquals(change_workload_relation.days_of_week_list, [1,2,4])
        self.assertEquals(change_workload_relation.base.operation_type_name_id, self.operation_type_name1.id)
        self.assertEquals(change_workload_relation.depended.operation_type_name_id, self.operation_type_name3.id)
        self.assertEquals(change_workload_relation.max_value, 1.0)
        self.assertEquals(change_workload_relation.threshold, 0.4)
        self.assertEquals(change_workload_relation.order, 1)
        forecast_relation = OperationTypeRelation.objects.get(base__load_template=lt, type=OperationTypeRelation.TYPE_PREDICTION)
        self.assertEquals(forecast_relation.base.operation_type_name_id, self.operation_type_name2.id)
        self.assertEquals(forecast_relation.depended.operation_type_name_id, self.operation_type_name4.id)

    def _test_upload_errors(self, data, error_msg):
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter') # TODO: move to openpyxl
        pd.DataFrame(data).to_excel(excel_writer=writer, sheet_name='Load template', index=False)
        writer.book.close()
        output.seek(0)
        response = self.client.post(
            '/rest_api/load_template/upload/',
            {
                'name': 'Test2',
                'file': SimpleUploadedFile('template.xlsx', output.read())
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), error_msg)
        self.assertIsNone(LoadTemplate.objects.filter(name='Test2').first())

    def test_upload_errors(self):
        data = [
            {
                'Тип операции': 'Кассы', 
                'Зависимости': 'Строительные работы', 
                'Формула': 'a * 2 + a', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '0,1,2,3,4,5,6', 
                'Шаг прогноза': '', 
                'Время начала': '', 
                'Время окончания': '', 
            }, 
            {
                'Тип операции': '', 
                'Зависимости': 'ДМ', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': 1.0, 
                'Порог': 0.4, 
                'Порядок': 1, 
                'Дни недели (через запятую)': '1,2,4', 
                'Шаг прогноза': '', 
                'Время начала': '', 
                'Время окончания': '', 
            }, 
            {
                'Тип операции': 'Строительные работы', 
                'Зависимости': '', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '', 
            }, 
            {
                'Тип операции': 'Пробитие чека', 
                'Зависимости': '', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '', 
            }, 
            {
                'Тип операции': 'ДМ', 
                'Зависимости': '', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '', 
            },
            {
                'Тип операции': 'Продажи', 
                'Зависимости': '', 
                'Формула': '', 
                'Константа': '', 
                'Максимальное значение': '', 
                'Порог': '', 
                'Порядок': '', 
                'Дни недели (через запятую)': '', 
                'Шаг прогноза': '1h', 
                'Время начала': '', 
                'Время окончания': '', 
            },
        ]
        self._test_upload_errors(data, ['Ошибка в строке 2. Шаг прогноза обязателен.'])
        data[0]['Шаг прогноза'] = '11h'
        self._test_upload_errors(data, ['Ошибка в строке 2. Шаг прогноза 11h не является валидным, следует выбрать из 1h, 30min, 1d.'])
        data[0]['Шаг прогноза'] = '1h'
        data[0]['Формула'] = ''
        self._test_upload_errors(data, ['Ошибка в строке 2. Формула обязательна в отношении Кассы -> Строительные работы'])
        data[0]['Формула'] = 'a * 2 , a'
        self._test_upload_errors(data, ['Ошибка в строке 2. Ошибка в формуле: a * 2 , a'])
        data[0]['Формула'] = 'a * 2 + a'
        data[5]['Зависимости'] = 'Строительные работы'
        self._test_upload_errors(data, ['Ошибка в строке 7. Тип операции для помощи в прогнозе Продажи не может иметь зависимостей.'])
        data[5]['Зависимости'] = ''
        data[4]['Зависимости'] = 'Продажи'
        data[4]['Формула'] = 'a * 2'
        self._test_upload_errors(data, ['Ошибка в строке 6. Только прогнозируемые типы операций могут зависеть от операций для помощи в прогнозе.'])
        data[4]['Зависимости'] = ''
        data[4]['Формула'] = ''
        data[3]['Зависимости'] = 'ДМ'
        data[3]['Формула'] = 'a * 2'
        self._test_upload_errors(data, ['Ошибка в строке 5. Тип операции Пробитие чека не может зависеть от типа работ ДМ.'])
        data[3]['Завивимости'] = ''
        data[3]['Формула'] = ''
        data[4]['Зависимости'] = 'Входящие'
        self._test_upload_errors(data, ['Данные типы операций есть в зависимостях, но отсутствуют в списке операций: Входящие.'])
        data[4]['Зависимости'] = ''
        data[2]['Зависимости'] = 'ДМ'
        self._test_upload_errors(data, ['Ошибка в строке 4. Прогнозируемый тип Строительные работы не может зависеть от ДМ с типом расчета по формуле.'])
        data[1]['Максимальное значение'] = ''
        self._test_upload_errors(data, ["Ошибка в строке 3. Для отношения 'перекидывание нагрузки между типами работ' максимальное значение обязательны."])
        data[1]['Порог'] = ''
        data[1]['Дни недели (через запятую)'] = '1,2'
        self._test_upload_errors(data, ["Ошибка в строке 3. Для отношения 'перекидывание нагрузки между типами работ' максимальное значение, порог обязательны."])
        