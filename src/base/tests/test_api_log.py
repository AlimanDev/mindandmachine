from datetime import date

from freezegun import freeze_time
from rest_framework.test import APITestCase

from src.base.models import (
    User,
    Shop,
    WorkerPosition,
    Employment,
    ApiLog,
)
from src.base.tests.factories import (
    NetworkFactory,
    GroupFactory,
    EmployeeFactory,
    ShopFactory,
    EmploymentFactory,
)
from src.util.mixins.tests import TestsHelperMixin


class TestApiLog(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(settings_values=cls.dump_data({
            "api_log_settings": {
                "log_funcs": {
                    "User": {
                        "by_code": True,
                        "http_methods": ['POST', 'PUT'],
                        "save_response_codes": [400],
                    },
                    "Shop": {
                        "by_code": True,
                        "http_methods": ['POST', 'PUT'],
                        "save_response_codes": [400],
                    },
                    "WorkerPosition": {
                        "by_code": True,
                        "http_methods": ['POST', 'PUT'],
                        "save_response_codes": [400],
                    },
                    "Employment": {
                        "by_code": True,
                        "http_methods": ['POST', 'PUT'],
                        "save_response_codes": [400],
                    },
                }
            }
        }))
        cls.api_employee = EmployeeFactory(user__network=cls.network)
        cls.group = GroupFactory(network=cls.network)
        cls.shop = ShopFactory(network=cls.network, code='main')
        cls.employment = EmploymentFactory(shop=cls.shop, employee=cls.api_employee, function_group=cls.group)
        cls.add_group_perm(cls.group, 'User', 'PUT')
        cls.add_group_perm(cls.group, 'Shop', 'PUT')
        cls.add_group_perm(cls.group, 'WorkerPosition', 'PUT')
        cls.add_group_perm(cls.group, 'Employment', 'PUT')

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.api_employee.user)

    def test_api_log_created(self):
        username = "НМ00-123456"
        response = self.client.put(
            path=self.get_url('User-detail', pk=username),
            data=self.dump_data({
                "first_name": " Иван",
                "last_name": " Иванов",
                "middle_name": "Иванович",
                "birthday": "2000-07-20",
                "username": username,
                "auth_type": "local",
                "by_code": True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        user = User.objects.filter(username=username).first()
        self.assertIsNotNone(user)

        shop_code = "3-001"
        response = self.client.put(
            path=self.get_url('Shop-detail', pk=shop_code),
            data=self.dump_data({
                "address": "ул. Кибальчича, д. 2. корп. 1",
                "by_code": True,
                "code": shop_code,
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
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        shop = Shop.objects.filter(code=shop_code).first()
        self.assertIsNotNone(shop)

        worker_position_code = 'doctor'
        response = self.client.put(
            path=self.get_url('WorkerPosition-detail', pk=worker_position_code),
            data=self.dump_data({
                'name': 'Врач',
                'code': worker_position_code,
                'by_code': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        worker_position = WorkerPosition.objects.filter(code=worker_position_code).first()
        self.assertIsNotNone(worker_position)

        employment_code = 'doctor'
        response = self.client.put(
            path=self.get_url('Employment-detail', pk=employment_code),
            data=self.dump_data({
                'position_code': worker_position_code,
                'dt_hired': '2021-01-01',
                'dt_fired': '3999-01-01',
                'shop_code': shop_code,
                'username': username,
                'code': employment_code,
                'tabel_code': username,
                'by_code': True,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        employment = Employment.objects.filter(code=employment_code).first()
        self.assertIsNotNone(employment)

        self.assertEqual(ApiLog.objects.count(), 4)

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=employment.id),
            data=self.dump_data({
                'dt_hired': '2021-01-10',
                'dt_fired': '3999-01-01',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        employment.refresh_from_db()
        self.assertEqual(employment.dt_hired, date(2021, 1, 10))

        self.assertEqual(ApiLog.objects.count(), 4)  # все еще 4, запрос без by_code не должен записаться

    def test_clean_old_api_log(self):
        username = "НМ00-123456"
        user_data = {
                "first_name": " Иван",
                "last_name": " Иванов",
                "middle_name": "Иванович",
                "birthday": "2000-07-20",
                "username": username,
                "auth_type": "local",
                "by_code": True,
            }
        with freeze_time('2021-06-15'):
            response = self.client.put(
                path=self.get_url('User-detail', pk=username),
                data=self.dump_data(user_data),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        user = User.objects.filter(username=username).first()
        self.assertIsNotNone(user)
        self.assertEqual(ApiLog.objects.count(), 1)

        user_data['middle_name'] = 'Иванович2'
        with freeze_time('2021-08-15'):
            response = self.client.put(
                path=self.get_url('User-detail', pk=username),
                data=self.dump_data(user_data),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ApiLog.objects.count(), 2)

        with freeze_time('2021-09-30'):
            ApiLog.clean_log(network_id=self.api_employee.user.network_id, delete_gap=60)
        self.assertEqual(ApiLog.objects.count(), 1)
