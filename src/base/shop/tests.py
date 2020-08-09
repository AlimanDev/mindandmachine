from datetime import datetime
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.base.models import Shop, FunctionGroup, ShopSettings
from src.timetable.models import ShopMonthStat

class TestDepartment(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/department/'

        create_departments_and_users(self)
        self.settings = ShopSettings.objects.first()


        self.shop_url = f"{self.url}{self.shop.id}/"
        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        # Админ
        response = self.client.get(self.url) # full tree
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        res = response.json()
        self.assertEqual(len(res), 1)
        self.assertEqual(len(res[0]['children']), 2)

        response = self.client.get(f"{self.url}?only_top=1" )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        shops = [
                {'id': 1,
                 'forecast_step_minutes': '00:30:00',
                 'label': 'Корневой магазин',
                 "tm_open_dict": '{"all":"06:00:00"}',
                 "tm_close_dict": '{"all":"23:00:00"}',
                 'children':[]
                 },
        ]
        self.assertEqual(response.json(), shops)

        # Сотрудник
        self.client.force_authenticate(user=self.user2)

        response = self.client.get(self.url) # full tree
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shops = response.json()
        self.assertEqual(len(shops), 1)
        self.assertEqual(shops[0]['id'], self.shop.id)

    def test_get(self):
        # Админ

        # Корневой магазин
        response = self.client.get(f"{self.url}{self.root_shop.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual( response.json()['id'], self.root_shop.id)


        # Обычный магазин
        response = self.client.get(f"{self.url}{self.shop2.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], self.shop2.id)

        # Сотрудник

        #Свой магазин
        self.client.force_authenticate(user=self.user2)


        response = self.client.get(f"{self.url}{self.shop.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], self.shop.id)

        response = self.client.get(f"{self.url}{self.root_shop.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.get(f"{self.url}{self.shop2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create(self):
        data = {
            "area":None,
            "parent_id": self.root_shop.id,
            "name": 'Region Shop3',
            "tm_open_dict": '{"all":"07:00:00"}',
            "tm_close_dict": '{"all":"23:00:00"}',
            "region_id": self.region.id,
            "restricted_end_times": '[]',
            "restricted_start_times": '[]',
            "settings_id": self.settings.id,
            "code": None,
            "address": None,
            "type": 's',
            "dt_opened": '2019-01-01',
            # "dt_closed": None,
            "timezone": 'Europe/Moscow',
            'restricted_end_times': '[]',
            'restricted_start_times': '[]',
            'settings_id': self.settings.id,
        }
        # response = self.client.post(self.url, data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='Shop',
            level_up=1,
            level_down=99,
        )

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        shop = response.json()
        data['id'] = shop['id']
        data['dt_closed'] = None
        data['load_template_id'] = None
        data['exchange_settings_id'] = None
        self.assertEqual(shop, data)

    def test_update(self):
        data = {
            "parent_id": self.root_shop.id,
            "name": 'Title 2',
            "tm_open_dict": '{"all":"07:00:00"}',
            "tm_close_dict": '{"all":"23:00:00"}',
            "region_id": self.region.id,
            "restricted_end_times": '[]',
            "restricted_start_times": '[]',
            "settings_id": self.settings.id,
            "code": "10",
            "address": 'address',
            "type": Shop.TYPE_REGION,
            "dt_opened": '2019-01-01',
            "dt_closed": "2020-01-01",
            "timezone": 'Europe/Berlin',
            'restricted_end_times': '[]',
            'restricted_start_times': '[]',
            'settings_id': self.settings.id,
            "area": None,
        }
        # response = self.client.put(self.shop_url, data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='Shop',
            level_up=1,
            level_down=99,
        )

        response = self.client.put(self.shop_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shop = response.json()
        data['id'] = shop['id']
        data['load_template_id'] = None
        data['exchange_settings_id'] = None
        self.assertEqual(shop, data)

    def test_stat(self):
        self.timetable1_1 = ShopMonthStat.objects.create(
            shop = self.shop,
            dt = datetime.now().date().replace(day=1),
            status = 1,
            dttm_status_change = datetime.now(),
            fot=10,
            idle=10,
            lack=10,
            workers_amount=10,
            revenue=10,
            fot_revenue=10,
        )
        self.timetable1_2 = ShopMonthStat.objects.create(
            shop = self.shop,
            dt = datetime.now().date().replace(day=1) - relativedelta(months=1),
            status = 1,
            dttm_status_change = datetime.now()- relativedelta(months=1),
            fot=5,
            idle=5,
            lack=5,
            workers_amount=5,
            revenue=5,
            fot_revenue=5,
        )

        response = self.client.get(f"{self.url}stat/?id={self.shop.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = [{
            'id': self.shop.id,
            'parent_id': self.reg_shop1.id,
            'name': 'Shop1',
            'fot_curr': 10.0,
            'fot_prev': 5.0,
            'revenue_prev': 5.0,
            'revenue_curr': 10.0,
            'lack_prev': 5.0,
            'lack_curr': 10.0}]

        self.assertEqual(response.json(), data)
