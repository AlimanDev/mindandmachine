from datetime import datetime, date

from rest_framework import status
from rest_framework.test import APITestCase
from src.common.mixins.tests import TestsHelperMixin

from src.apps.timetable.models import ShopMonthStat
from src.common.models_converter import Converter

class TestShopMonthStat(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/shop_month_stat/'

        cls.create_departments_and_users()
        cls.month_stat = ShopMonthStat.objects.create(
            dt=date.today().replace(day=1),
            dttm_status_change=datetime.now(),
            shop_id=cls.shop.id,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 1)

    
    def test_get_by_dt_and_shop(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}&dt={Converter.convert_date(date.today().replace(day=1))}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 1)


    def test_get(self):
        response = self.client.get(f'{self.url}{self.month_stat.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.month_stat.id, 
            'shop_id': self.shop.id, 
            'status_message': None, 
            'dt': Converter.convert_date(date.today().replace(day=1)), 
            'status': 'N', 
            'fot': 0, 
            'lack': 0, 
            'idle': 0, 
            'workers_amount': 0, 
            'revenue': 0, 
            'fot_revenue': 0
        }
        
        self.assertEqual(response.json(), data)

    def test_update(self):
        data = {
            'fot': 10,
            'workers_amount': 30,
        }
        response = self.client.put(f'{self.url}{self.month_stat.id}/', data, format='json')
        month_stat = response.json()
        data['id'] = self.month_stat.id
        data.update(
            {
                'shop_id': self.shop.id, 
                'status_message': None, 
                'dt': Converter.convert_date(date.today().replace(day=1)), 
                'status': 'N', 
                'lack': 0, 
                'idle': 0, 
                'revenue': 0, 
                'fot_revenue': 0
            }
        )
        self.assertEqual(month_stat, data)

    
    def test_get_status(self):
        response = self.client.get(f'{self.url}status/?shop_id={self.shop.id}&dt={Converter.convert_date(date.today().replace(day=1))}')
        month_stat = response.json()
        data = {
            'id': self.month_stat.id, 
            'shop_id': self.shop.id, 
            'status_message': None, 
            'dt': Converter.convert_date(date.today().replace(day=1)), 
            'status': 'N', 
            'fot': 0, 
            'lack': 0, 
            'idle': 0, 
            'workers_amount': 0, 
            'revenue': 0, 
            'fot_revenue': 0
        }
        self.assertEqual(month_stat, data)
        