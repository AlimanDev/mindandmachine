from datetime import datetime, timedelta, time
from rest_framework import status
from rest_framework.test import APITestCase
from dateutil.relativedelta import relativedelta
from src.util.test import create_departments_and_users
from src.util.models_converter import Converter
from src.forecast.models import OperationTypeName, OperationType, OperationTemplate
from src.timetable.models import WorkTypeName, WorkType
from src.base.models import FunctionGroup


class TestOperationTemplate(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/operation_template/'

        create_departments_and_users(self)
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        self.work_type1 = WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name1)
        self.work_type2 = WorkType.objects.create(shop=self.shop2, work_type_name=self.work_type_name1)

        self.operation_type_name1 = OperationTypeName.objects.create(
            name='продажа',
        )

        self.operation_type_name2 = OperationTypeName.objects.create(
            name='продажа2',
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

        self.dt_from = datetime.now().date() + timedelta(days=5)

        self.ot_daily = OperationTemplate.objects.create(
            operation_type=self.operation_type,
            name='Ежедневный',
            period=OperationTemplate.PERIOD_DAILY,
            days_in_period=[], #не используются в ежедневном шаблоне
            tm_start=time(10),
            tm_end=time(12),
            value=2.25
        )
        self.ot_weekly = OperationTemplate.objects.create(
            operation_type=self.operation_type,
            name='Еженедельный',
            period=OperationTemplate.PERIOD_WEEKLY,
            days_in_period=[2,3,7],
            tm_start=time(10),
            tm_end=time(12),
            value=2.25
        )
        self.ot_monthly = OperationTemplate.objects.create(
            operation_type=self.operation_type,
            name='Ежемесячный',
            period=OperationTemplate.PERIOD_MONTHLY,
            days_in_period=[1,3,7,15,28,31],
            tm_start=time(10,30),
            tm_end=time(13),
            value=3.25
        )

        self.ot_monthly2 = OperationTemplate.objects.create(
            operation_type=self.operation_type2,
            name='Ежемесячный2',
            period=OperationTemplate.PERIOD_MONTHLY,
            days_in_period=[1,3,7,15,28,31],
            tm_start=time(10,30),
            tm_end=time(13),
            value=3.25
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}')
        self.assertEqual(len(response.json()), 3)
        response = self.client.get(f'{self.url}?operation_type_id={self.operation_type2.id}')
        self.assertEqual(len(response.json()), 1)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.ot_monthly.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.ot_monthly.id, 
            'operation_type_id': self.operation_type.id, 
            'tm_start': '10:30:00', 
            'tm_end': '13:00:00', 
            'period': 'M', 
            'days_in_period': [1, 3, 7, 15, 28, 31], 
            'dt_built_to': None, 
            'value': 3.25, 
            'name': 'Ежемесячный', 
            'code': ''
        }
        self.assertEqual(response.json(), data)

    def test_create(self):
        data = {
            'value': 2.25,
            'name':'Еженедельный',
            'tm_start': '10:00:00',
            'tm_end': '12:00:00',
            'period': 'W',
            'days_in_period': [2,3,7],
            'operation_type_id': self.operation_type.id,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        operation_template = response.json()
        data['id'] = operation_template['id']
        data['dt_built_to'] = Converter.convert_date(datetime.now().date() + timedelta(days=64))
        data['code'] = ''
        self.assertEqual(operation_template, data)

    def test_update(self):
        data = {
            'value': 3.25,
            'name':'Ежемесячный',
            'tm_start': '10:30:00',
            'tm_end': '13:00:00',
            'period': OperationTemplate.PERIOD_MONTHLY,
            'days_in_period': [1,2,4,15,20],
            'date_rebuild_from': self.dt_from,
        }
        response = self.client.put(f'{self.url}{self.ot_monthly.id}/', data, format='json')
        operation_template = response.json()
        data = {
            'id': self.ot_monthly.id, 
            'operation_type_id': self.operation_type.id, 
            'tm_start': '10:30:00', 
            'tm_end': '13:00:00', 
            'period': 'M', 
            'days_in_period': [1, 2, 4, 15, 20],
            'dt_built_to': None, 
            'value': 3.25, 
            'name': 'Ежемесячный', 
            'code': ''
        }
        self.assertEqual(operation_template, data)

    def test_update_incorrect(self):
        data = {
            'value': 3.25,
            'name':'Ежемесячный',
            'tm_start': '10:30:00',
            'tm_end': '13:00:00',
            'period': OperationTemplate.PERIOD_MONTHLY,
            'days_in_period': ["a","b"],
            'date_rebuild_from': self.dt_from,
        }
        response = self.client.put(f'{self.url}{self.ot_monthly.id}/', data, format='json')
        self.assertEqual(response.json(), {
            'days_in_period': {
                '0': ['Требуется целочисленное значение.'],
                '1': ['Требуется целочисленное значение.']
            }
        })
        data['days_in_period'] = [1,2,4,15,20,50]
        response = self.client.put(f'{self.url}{self.ot_monthly.id}/', data, format='json')
        self.assertEqual(response.json(), ['Перечисленные дни не соответствуют периоду'])

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.ot_monthly.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(OperationTemplate.objects.get(id=self.ot_monthly.id).dttm_deleted)