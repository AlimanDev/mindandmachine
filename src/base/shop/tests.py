from datetime import datetime

from dateutil.relativedelta import relativedelta
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import Shop, ShopSettings
from src.forecast.tests.factories import LoadTemplateFactory
from src.timetable.models import ShopMonthStat
from src.util.mixins.tests import TestsHelperMixin


class TestDepartment(TestsHelperMixin, APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/department/'

        cls.create_departments_and_users()
        cls.settings = ShopSettings.objects.first()
        cls.load_template = LoadTemplateFactory(network=cls.network)

        cls.root_shop.code = "main"
        cls.root_shop.save(update_fields=('code',))

        cls.shop_url = f'{cls.url}{cls.shop.id}/'

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    @staticmethod
    def _get_shop_data():
        return {
            "address": "Воронежская обл, г Воронеж, пр-кт Революции, д 48",
            "by_code": True,
            "code": "383-1",
            "dt_closed": "3001-01-01",
            "dt_opened": "2020-08-17",
            "name": "ООО \"НИКАМЕД\" ОРТЕКА  Воронеж Революции 48",
            "parent_code": "main",
            "timezone": "Europe/Moscow",
            "tm_close_dict": {
                "all": "00:00:00"
            },
            "tm_open_dict": {
                "all": "00:00:00"
            }
        }

    def test_create_department(self):
        resp = self.client.post(self.url, data=self.dump_data(self._get_shop_data()), content_type='application/json')
        self.assertEqual(resp.status_code, 201)

    def test_create_and_update_department_with_put_by_code(self):
        shop_data = self._get_shop_data()
        put_url = f'{self.url}{shop_data["code"]}/'
        resp = self.client.put(put_url, data=self.dump_data(shop_data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)

        resp = self.client.put(put_url, data=self.dump_data(shop_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_get_list(self):
        # Админ
        response = self.client.get(f'{self.url}tree/')  # full tree
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        res = response.json()
        self.assertEqual(len(res), 1)
        self.assertEqual(len(res[0]['children']), 2)

        # response = self.client.get(f"{self.url}tree/?only_top=1")
        # self.assertEqual(response.status_code, status.HTTP_200_OK)
        #
        # shops = [
        #     {'id': 1,
        #      'forecast_step_minutes': '00:30:00',
        #      'label': 'Корневой магазин',
        #      'address': None,
        #      "tm_open_dict": {"all": "06:00:00"},
        #      "tm_close_dict": {"all": "23:00:00"},
        #      'children': []
        #      },
        # ]
        # self.assertDictEqual(response.json(), shops)

        # Сотрудник
        self.client.force_authenticate(user=self.user2)

        response = self.client.get(self.url)  # full tree
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shops = response.json()
        # self.assertEqual(len(shops), 1)
        # self.assertEqual(shops[0]['id'], self.shop.id)

    def test_get(self):
        # Админ

        # Корневой магазин
        response = self.client.get(f"{self.url}{self.root_shop.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], self.root_shop.id)

        # Обычный магазин
        response = self.client.get(f"{self.url}{self.shop2.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], self.shop2.id)

        # Сотрудник

        # Свой магазин
        self.client.force_authenticate(user=self.user2)

        response = self.client.get(f"{self.url}{self.shop.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['id'], self.shop.id)

        # response = self.client.get(f"{self.url}{self.root_shop.id}/")
        # self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        #
        # response = self.client.get(f"{self.url}{self.shop2.id}/")
        # self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create(self):
        data = {
            "parent_id": self.root_shop.id,
            "name": 'Region Shop3',
            "tm_open_dict": {"all": "07:00:00"},
            "tm_close_dict": {"all": "23:00:00"},
            "region_id": self.region.id,
            "code": None,
            "address": None,
            "type": 's',
            "dt_opened": '2019-01-01',
            # "dt_closed": None,
            "timezone": 'Europe/Moscow',
            'restricted_end_times': '[]',
            'restricted_start_times': '[]',
            'settings_id': self.shop_settings.id,
            'forecast_step_minutes': '00:30:00',
        }
        # response = self.client.post(self.url, data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        shop = response.json()
        data['id'] = shop['id']
        data['area'] = 0.0
        data['dt_closed'] = None
        data['load_template_id'] = None
        data['load_template_status'] = 'R'
        data['exchange_settings_id'] = None
        self.assertDictEqual(shop, data)

    def test_update(self):
        data = {
            "parent_id": self.root_shop.id,
            "name": 'Title 2',
            "tm_open_dict": {"all": "07:00:00"},
            "tm_close_dict": {"all": "23:00:00"},
            "region_id": self.region.id,
            "code": "10",
            "address": 'address',
            "type": Shop.TYPE_REGION,
            "dt_opened": '2019-01-01',
            "dt_closed": "2020-01-01",
            "timezone": 'Europe/Berlin',
            'restricted_end_times': '[]',
            'restricted_start_times': '[]',
            'settings_id': self.shop_settings.id,
            'forecast_step_minutes': '00:30:00',
        }
        # response = self.client.put(self.shop_url, data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.put(self.shop_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shop = response.json()
        data['id'] = shop['id']
        data['area'] = 0.0
        data['load_template_id'] = None
        data['exchange_settings_id'] = None
        data['load_template_status'] = 'R'
        self.assertEqual(shop, data)

    def test_update_without_tm_open_close_dict_dont_clean_it(self):
        prev_tm_open_dict_val = self.shop.tm_open_dict
        prev_tm_close_dict_val = self.shop.tm_close_dict
        data = {
            'id': self.shop.id,
            'restricted_start_times': '["12:00"]',
            'restricted_end_times': '["20:40"]',
            'settings_id': self.shop_settings.id,
            'load_template_id': self.load_template.id,
            'name': 'Имя магазина',
            'timezone': 'Europe/Moscow',
        }

        response = self.client.put(self.shop_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.tm_open_dict, prev_tm_open_dict_val)
        self.assertEqual(self.shop.tm_close_dict, prev_tm_close_dict_val)

    def test_stat(self):
        self.timetable1_1 = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=datetime.now().date().replace(day=1),
            status=1,
            dttm_status_change=datetime.now(),
            fot=10,
            idle=10,
            lack=10,
            workers_amount=10,
            revenue=10,
            fot_revenue=10,
        )
        self.timetable1_2 = ShopMonthStat.objects.create(
            shop=self.shop,
            dt=datetime.now().date().replace(day=1) - relativedelta(months=1),
            status=1,
            dttm_status_change=datetime.now() - relativedelta(months=1),
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
