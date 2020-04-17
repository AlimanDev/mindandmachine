from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.timetable.models import ShopMonthStat
from src.base.models import FunctionGroup
from src.util.models_converter import Converter

class TestShopMonthStat(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/shop_month_stat/'

        create_departments_and_users(self)
        self.month_stat = ShopMonthStat.objects.create(
            dt=date.today().replace(day=1),
            dttm_status_change=datetime.now(),
            shop_id=self.shop.id,
        )
        
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='ShopMonthStat',
            level_up=1,
            level_down=99,
        )

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
        