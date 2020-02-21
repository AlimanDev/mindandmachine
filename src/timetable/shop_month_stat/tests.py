from datetime import datetime
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.timetable.models import ShopMonthStat
from src.base.models import FunctionGroup


class TestWorkTypeName(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/shop_month_stat/'

        create_departments_and_users(self)
        
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='ShopMonthStat',
            level_up=1,
            level_down=99,
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 4)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.work_type_name1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {'name': 'Кассы', 'code': None}
        data['id'] = response.json()['id']
        self.assertEqual(response.json(), data)

    def test_update(self):
        data = {
            'name': 'Склад',
            'code': '21',
        }
        response = self.client.put(f'{self.url}{self.work_type_name1.id}/', data, format='json')
        work_type_name = response.json()
        data['id'] = self.work_type_name1.id
        self.assertEqual(work_type_name, data)
        