from datetime import datetime
from decimal import Decimal
from unittest import mock

from dadata import Dadata
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.models import Shop, ShopSchedule, NetworkConnect, Network, Employment, Group
from src.base.tests.factories import UserFactory, ShopFactory
from src.forecast.tests.factories import LoadTemplateFactory
from src.timetable.models import ShopMonthStat
from src.util.mixins.tests import TestsHelperMixin


class TestDepartment(TestsHelperMixin, APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/department/'

        cls.create_departments_and_users()
        cls.load_template = LoadTemplateFactory(network=cls.network)

        cls.root_shop.code = "main"
        cls.root_shop.save(update_fields=('code',))

        cls.shop_url = f'{cls.url}{cls.shop.id}/'

    def setUp(self):
        self.client.force_authenticate(user=self.user1)
        self.network.refresh_from_db()

    @staticmethod
    def _get_shop_data():
        return {
            "address": "ул. Кибальчича, д. 2. корп. 1",
            "by_code": True,
            "code": "3-001",
            "dt_closed": "3001-01-01",
            "dt_opened": "2016-09-27",
            "name": "ООО \"НИКАМЕД\" ОРТЕКА  ВДНХ",
            "parent_code": "main",
            "timezone": "Europe/Moscow",
            "tm_close_dict": {
                "d0": "21:00:00",
                "d1": "21:00:00",
                "d2": "21:00:00",
                "d3": "21:00:00",
                "d4": "21:00:00",
                "d5": "21:00:00",
                "d6": "21:00:00"
            },
            "tm_open_dict": {
                "d0": "09:00:00",
                "d1": "09:00:00",
                "d2": "09:00:00",
                "d3": "09:00:00",
                "d4": "09:00:00",
                "d5": "09:00:00",
                "d6": "09:00:00"
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

        resp = self.client.put(put_url, data=self.dump_data(shop_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(Shop.objects.filter(code=shop_data["code"]).count(), 1)

    def test_cant_create_multiple_shops_with_the_same_code(self):
        shop_data = self._get_shop_data()
        resp = self.client.post(self.url, data=self.dump_data(shop_data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)

        resp = self.client.post(self.url, data=self.dump_data(shop_data), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

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
        nonstandard_schedule = [
            {
                "dt": "2021-01-01",
                "opens": None,
                "closes": None,
                "type": "H",
            },
            {
                "dt": "2021-01-02",
                "opens": "09:00:00",
                "closes": "19:00:00",
                "type": "W",
            },
            {
                "dt": "2021-01-09",
                "opens": "00:00:00",
                "closes": "00:00:00",
                "type": "W",
            },
        ]

        data = {
            "parent_code": self.root_shop.code,
            "name": 'Region Shop3',
            "tm_open_dict": {"all": "07:00:00"},
            "tm_close_dict": {"all": "23:00:00"},
            "nonstandard_schedule": nonstandard_schedule,
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
            'is_active': True,
            'director_code': self.user2.username,
            'distance': None,
        }
        # response = self.client.post(self.url, data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        shop = response.json()
        data['id'] = shop['id']
        data['parent_id'] = self.root_shop.id
        data.pop('parent_code')
        data['director_id'] = self.user2.id
        data['area'] = 0.0
        data['dt_closed'] = None
        data['load_template_id'] = None
        data['load_template_status'] = 'R'
        data['exchange_settings_id'] = None
        data['fias_code'] = ''
        data['latitude'] = None
        data['longitude'] = None
        data['distance'] = None
        data['email'] = None
        data.pop('director_code')
        data.pop('nonstandard_schedule')
        self.assertDictEqual(shop, data)

        for schedule_dict in nonstandard_schedule:
            schedule = ShopSchedule.objects.filter(
                shop_id=shop['id'],
                dt=schedule_dict['dt'],
            ).first()
            self.assertIsNotNone(schedule)
            self.assertEqual(str(schedule.opens), str(schedule_dict['opens']))
            self.assertEqual(str(schedule.closes), str(schedule_dict['closes']))
            self.assertEqual(str(schedule.type), str(schedule_dict['type']))
            self.assertEqual(schedule.modified_by_id, self.user1.id)

    def test_update(self):
        data = {
            "parent_id": self.root_shop.id,
            "name": 'Title 2',
            "tm_open_dict": {"all": "07:00:00"},
            "tm_close_dict": {"all": "23:00:00"},
            "nonstandard_schedule": [],
            "region_id": self.region.id,
            "code": "10",
            "email": "example@email.com",
            "address": 'address',
            "type": Shop.TYPE_REGION,
            "dt_opened": '2019-01-01',
            "dt_closed": "2020-01-01",
            "timezone": 'Europe/Berlin',
            'restricted_end_times': '[]',
            'restricted_start_times': '[]',
            'settings_id': self.shop_settings.id,
            'forecast_step_minutes': '00:30:00',
            'is_active': False,
            'latitude': '52.22967541',
            'longitude': '21.01222831',
            'director_code': 'nonexistent',
            'fias_code': '09d9d44f-044b-4b9a-97b0-c70f0e327e9f',
        }
        # response = self.client.put(self.shop_url, data, format='json')
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.put(self.shop_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shop = response.json()
        data['id'] = shop['id']
        data['director_id'] = None
        data['area'] = 0.0
        data['load_template_id'] = None
        data['exchange_settings_id'] = None
        data['distance'] = None
        data['load_template_status'] = 'R'
        data.pop('nonstandard_schedule')
        data.pop('director_code')
        self.assertEqual(shop, data)
        self.assertIsNotNone(Shop.objects.get(id=shop['id']).dttm_deleted)

    def test_400_resp_for_unexistent_parent_code(self):
        data = {
            "parent_code": 'nonexistent',
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
            'is_active': False,
            'latitude': '52.229675',
            'longitude': '21.012228',
            'director_code': 'nonexistent',
        }
        response = self.client.put(self.shop_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), ["Подразделение с parent_code=nonexistent не найдено"])

    def test_cant_save_with_invalid_restricted_times(self):
        data = {
            'id': self.shop.id,
            'restricted_start_times': '[false, ""]',
            'restricted_end_times': '[false]',
            'settings_id': self.shop_settings.id,
            'load_template_id': self.load_template.id,
            'name': 'Имя магазина',
            'timezone': 'Europe/Moscow',
        }

        resp = self.client.put(self.shop_url, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp_data = resp.json()
        self.assertIn('restricted_start_times', resp_data)
        self.assertIn('restricted_end_times', resp_data)

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

    def test_get_shops_with_distance(self):
        self.shop.latitude = 51.229675
        self.shop.longitude = 21.012228
        self.shop.save()
        self.shop2.latitude = 52.129675
        self.shop2.longitude = 22.412228
        self.shop2.save()
        response = self.client.get(
            self.url,
            data={'id__in': f'{self.shop.id},{self.shop2.id},{self.shop3.id}'},
            **{'X-LAT': 52.229675, 'X-LON': 21.012228}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        shops = sorted(response.json(), key=lambda i: i['id'])
        self.assertEqual(len(shops), 3)
        self.assertEqual(shops[0]['distance'], 111.26)
        self.assertEqual(shops[1]['distance'], 96.41)
        self.assertEqual(shops[2]['distance'], None)

    def test_get_shops_without_deleted_and_closed(self):
        self.assertEqual(Shop.objects.count(), 6)
        self.shop.dttm_deleted = datetime(2020, 1, 1)
        self.shop.save()
        self.shop2.dt_closed = datetime(2020, 1, 1).date()
        self.shop2.save()
        response = self.client.get(self.url + 'tree/')
        response = response.json()
        self.assertEqual(len(response[0]['children'][0]['children']), 0)
        self.assertEqual(len(response[0]['children'][1]['children']), 1)

    def test_get_shops_ordered_by_name(self):
        response = self.client.get(self.url + 'tree/')
        response = response.json()
        self.assertEqual(response[0]['children'][0]['label'], 'Region Shop1')
        self.assertEqual(response[0]['children'][1]['label'], 'Region Shop2')
        self.assertEqual(response[0]['children'][0]['children'][0]['label'], 'Shop1')
        self.assertEqual(response[0]['children'][0]['children'][1]['label'], 'Shop2')
        self.assertEqual(response[0]['children'][1]['children'][0]['label'], 'Shop3')

    
    def test_cant_change_load_template(self):
        self.shop.load_template_status = Shop.LOAD_TEMPLATE_PROCESS
        self.shop.save()
        response = self.client.put(f'{self.url}{self.shop.id}/', data={'load_template_id': self.load_template.id, 'name': 'Shop Test'})
        self.assertEqual(response.json(), ['Невозможно изменить шаблон нагрузки, так как он находится в процессе расчета.'])

    def test_shop_schedule_filled_on_shop_creating(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                shop = Shop.objects.create(
                    parent=self.reg_shop1,
                    name='New shop',
                    tm_open_dict='{"all":"07:00:00"}',
                    tm_close_dict='{"all":"23:00:00"}',
                    region=self.region,
                    settings=self.shop_settings,
                    network=self.network,
                )
        self.assertEqual(ShopSchedule.objects.filter(shop=shop).count(), 120)

    def test_shop_city_filled_on_creation_from_dadata(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True, DADATA_TOKEN='dummy', FILL_SHOP_CITY_FROM_COORDS=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                with mock.patch.object(Dadata, 'geolocate') as mock_geolocate:
                    mock_geolocate.return_value = [
                        {
                            "data": {"city": "city_name",}
                        },
                    ]
                    shop = Shop.objects.create(
                        parent=self.reg_shop1,
                        name='New shop',
                        tm_open_dict='{"all":"07:00:00"}',
                        tm_close_dict='{"all":"23:00:00"}',
                        region=self.region,
                        settings=self.shop_settings,
                        network=self.network,
                        latitude=56,
                        longitude=35,
                        city=None,
                    )
        shop.refresh_from_db(fields=['city'])
        self.assertEqual(shop.city, 'city_name')

    def test_shop_city_not_filled_if_no_results(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True, DADATA_TOKEN='dummy', FILL_SHOP_CITY_FROM_COORDS=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                with mock.patch.object(Dadata, 'geolocate') as mock_geolocate:
                    mock_geolocate.return_value = []
                    shop = Shop.objects.create(
                        parent=self.reg_shop1,
                        name='New shop',
                        tm_open_dict='{"all":"07:00:00"}',
                        tm_close_dict='{"all":"23:00:00"}',
                        region=self.region,
                        settings=self.shop_settings,
                        network=self.network,
                        latitude=56,
                        longitude=35,
                        city=None,
                    )
        shop.refresh_from_db(fields=['city'])
        self.assertEqual(shop.city, None)

    def test_shop_city_filled_after_coords_adding(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True, DADATA_TOKEN='dummy', FILL_SHOP_CITY_FROM_COORDS=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                with mock.patch.object(Dadata, 'geolocate') as mock_geolocate:
                    mock_geolocate.return_value = [
                        {
                            "data": {"city": "city_name",}
                        },
                    ]
                    shop = Shop.objects.create(
                        parent=self.reg_shop1,
                        name='New shop',
                        tm_open_dict='{"all":"07:00:00"}',
                        tm_close_dict='{"all":"23:00:00"}',
                        region=self.region,
                        settings=self.shop_settings,
                        network=self.network,
                        city=None,
                    )
                    mock_geolocate.assert_not_called()
                    shop.refresh_from_db(fields=['city'])
                    self.assertEqual(shop.city, None)

                    shop.latitude = 56
                    shop.longitude = 35
                    shop.save()
                    mock_geolocate.called_once_with(latitude=56, longitude=35)

        shop.refresh_from_db(fields=['city'])
        self.assertEqual(shop.city, 'city_name')

    def test_city_coords_address_timezone_filled_from_dadata_by_fias_code(self):
        with self.settings(
                CELERY_TASK_ALWAYS_EAGER=True,
                DADATA_TOKEN='dummy',
                FILL_SHOP_CITY_COORDS_ADDRESS_TIMEZONE_FROM_FIAS_CODE=True
        ):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                with mock.patch.object(Dadata, 'find_by_id') as mock_find_by_id:
                    mock_find_by_id.return_value = [
                        {
                            "data": {
                                "city": "Новосибирск",
                                "geo_lat": "55.0286283",
                                "geo_lon": "82.9102479",
                            },
                            "value": "г Новосибирск, ул Ленина, д 15",
                        },
                    ]
                    shop = Shop.objects.create(
                        parent=self.reg_shop1,
                        name='New shop',
                        tm_open_dict='{"all":"07:00:00"}',
                        tm_close_dict='{"all":"23:00:00"}',
                        region=self.region,
                        settings=self.shop_settings,
                        network=self.network,
                        city=None,
                        address='новосибирск ленина 15',
                        fias_code='',
                    )
                    mock_find_by_id.assert_not_called()
                    shop.refresh_from_db()
                    self.assertEqual(shop.city, None)

                    shop.fias_code = '09d9d44f-044b-4b9a-97b0-c70f0e327e9f'
                    shop.save()
                    mock_find_by_id.called_once_with("address", "09d9d44f-044b-4b9a-97b0-c70f0e327e9f")

        shop.refresh_from_db()
        self.assertEqual(shop.city, 'Новосибирск')
        self.assertEqual(shop.latitude, Decimal('55.0286283'))
        self.assertEqual(shop.longitude, Decimal('82.9102479'))
        self.assertEqual(shop.address, 'г Новосибирск, ул Ленина, д 15')
        self.assertEqual(shop.timezone.zone, 'Asia/Novosibirsk')

    def test_get_outsource_shops_tree(self):
        def _create_shop(name, network, parent=None):
            return Shop.objects.create(
                name=name,
                region=self.region,
                network=network,
                parent=parent,
            )
        def _create_network_and_shops(name, count_of_shops):
            network = Network.objects.create(
                name=name,
            )
            root_shop = _create_shop(name, network)
            shops = []
            for i in range(count_of_shops):
                shops.append(_create_shop(f'{name}_магазин{i+1}', network, root_shop))
            return network, root_shop, shops
        client_network1, client1_root_shop, client1_shops = _create_network_and_shops('Клиент1', 2)
        client_network2, client2_root_shop, client2_shops = _create_network_and_shops('Клиент2', 1)
        client_network3, client3_root_shop, client3_shops = _create_network_and_shops('Клиент3', 3)
        NetworkConnect.objects.create(client=client_network1, outsourcing=self.network)
        NetworkConnect.objects.create(client=client_network2, outsourcing=self.network)

        response = self.client.get(self.url + 'outsource_tree/')
        response = response.json()
        self.assertEqual(len(response), 2)
        self.assertEqual(response[0]['label'], 'Клиент1')
        self.assertEqual(len(response[0]['children']), 2)
        self.assertEqual(response[1]['label'], 'Клиент2')
        self.assertEqual(len(response[1]['children']), 1)

    def test_ignore_parent_code_when_updating_department_via_api_parameter(self):
        shop_data = self._get_shop_data()
        put_url = f'{self.url}{shop_data["code"]}/'

        response = self.client.put(put_url, shop_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        shop = Shop.objects.get(code=shop_data['code'])
        self.assertEqual(shop.parent_id, self.root_shop.id)

        shop.parent = self.reg_shop1
        shop.save()

        response = self.client.put(put_url, shop_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        shop.refresh_from_db()
        # при выключенной настройке родитель должен обновиться
        self.assertEqual(
            shop.parent_id,
            self.root_shop.id
        )

        shop.parent = self.reg_shop1
        shop.save()

        shop.network.ignore_parent_code_when_updating_department_via_api = True
        shop.network.save()

        response = self.client.put(put_url, shop_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        shop.refresh_from_db()
        # при включенной настройке родитель не должен обновиться
        self.assertEqual(
            shop.parent_id,
            self.reg_shop1.id
        )

    def test_create_employment_on_set_or_update_director_code(self):
        urs_group, _urs_group_created = Group.objects.get_or_create(name='УРС', code='urs', network=self.network)
        self.network.create_employment_on_set_or_update_director_code = True
        self._add_network_settings_value(self.network, 'shop_lvl_to_role_code_mapping', {
            0: 'urs',
            1: 'director',
        })
        self.network.save()

        director_code = 'IvanovII'
        director_user = UserFactory(username=director_code)
        shop_data = self._get_shop_data()
        shop_data['director_code'] = director_code
        put_url = f'{self.url}{shop_data["code"]}/'
        response = self.client.put(put_url, shop_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        employment = Employment.objects.filter(
            employee__user_id=director_user.id,
            is_visible=False, dt_hired=timezone.now(), dt_fired='3999-12-31',
        ).first()
        self.assertIsNotNone(employment)
        self.assertEqual(employment.function_group_id, self.chief_group.id)

        director_code2 = 'PetrovPP'
        director_user2 = UserFactory(username=director_code2)
        shop_data['director_code'] = director_code2
        response = self.client.put(put_url, shop_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employment = Employment.objects.filter(
            employee__user_id=director_user.id,
            function_group=self.chief_group,
            is_visible=False, dt_hired=timezone.now(), dt_fired='3999-12-31',
        ).first()
        self.assertIsNone(employment)
        employment2 = Employment.objects.filter(
            employee__user_id=director_user2.id,
            function_group=self.chief_group,
            is_visible=False, dt_hired=timezone.now(), dt_fired='3999-12-31',
        ).first()
        self.assertIsNotNone(employment2)

        shop_data = self._get_shop_data()
        shop_data['director_code'] = director_code
        shop_data['code'] = self.root_shop.code
        shop_data.pop('parent_code')
        put_url = f'{self.url}{shop_data["code"]}/'
        response = self.client.put(put_url, shop_data, format='json')
        self.print_resp(response)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        employment = Employment.objects.filter(
            employee__user_id=director_user.id,
            function_group=urs_group,
            is_visible=False, dt_hired=timezone.now(), dt_fired='3999-12-31',
        ).first()
        self.assertIsNotNone(employment)
        self.assertEqual(employment.function_group_id, urs_group.id)

    def test_force_create_director_employment(self):
        director_code = 'IvanovII'
        director_user = UserFactory(username=director_code)

        shop = ShopFactory(director=director_user)
        employment_qs = Employment.objects.filter(
            employee__user_id=director_user.id,
            function_group=self.chief_group,
            is_visible=False, dt_hired=timezone.now(), dt_fired='3999-12-31',
        )
        employment = employment_qs.first()
        self.assertIsNone(employment)

        shop.network.create_employment_on_set_or_update_director_code = True
        self._add_network_settings_value(shop.network, 'shop_lvl_to_role_code_mapping', {
            0: 'director',
        })
        shop.network.save()

        shop.save(force_create_director_employment=True)
        employment = employment_qs.first()
        self.assertIsNotNone(employment)

        shop.save(force_create_director_employment=True)
        employment_count = employment_qs.count()
        self.assertEqual(employment_count, 1)
