from datetime import timedelta
import json

from django.utils import timezone
from rest_framework.test import APITestCase
from unittest import mock

from src.recognition.api import recognition
from src.recognition.models import UserConnecter
from src.base.models import WorkerPosition, Employment, User, Network, NetworkConnect
from src.timetable.models import WorkTypeName
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter


class TestUserViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.worker_position = WorkerPosition.objects.create(
            name='Директор магазина',
            code='director',
            network=cls.network,
        )
        cls.wt_name = WorkTypeName.objects.create(name='test_name', code='test_code')
        cls.wt_name2 = WorkTypeName.objects.create(name='test_name2', code='test_code2')
        cls.worker_position.default_work_type_names.set([cls.wt_name, cls.wt_name2])
        cls.dt_now = timezone.now().today()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_and_then_edit_user_with_put(self):
        username = "НМ00-123456"
        data = {
            "first_name": " Иван",
            "last_name": " Иванов",
            "middle_name": "Иванович",
            "birthday": "2000-07-20",
            "avatar": "string",
            "phone_number": "string",
            "username": username,
            "auth_type": "local",
            "by_code": True,
        }
        resp = self.client.put(self.get_url('User-detail', pk=username), data=data)
        self.assertEqual(resp.status_code, 201)

        user = User.objects.filter(username=username).first()
        self.assertEqual(user.email, '')
        self.assertEqual(user.auth_type, 'local')

        data['email'] = 'email@example.com'
        data['auth_type'] = 'ldap'
        resp = self.client.put(self.get_url('User-detail', pk=username), data=data)
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, 'email@example.com')
        self.assertEqual(user.auth_type, 'ldap')

        data['auth_type'] = 'invalid'
        resp = self.client.put(self.get_url('User-detail', pk=username), data=data)
        self.assertEqual(resp.status_code, 400)

    def test_create_user_with_post(self):
        username = "НМ00-123456"
        data = {
            "first_name": " Иван",
            "last_name": " Иванов",
            "middle_name": "Иванович",
            "birthday": "2000-07-20",
            "avatar": "string",
            "phone_number": "string",
            "username": username,
            "by_code": True,
        }
        resp = self.client.put(self.get_url('User-detail', pk=username), data=data)
        self.assertEqual(resp.status_code, 201)

        user = User.objects.get(username=username)
        self.assertTrue(user.password == '')

    def test_get_list(self):
        resp = self.client.get(self.get_url('User-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 8)

    def test_get_users_only_with_active_employment(self):
        Employment.objects.exclude(employee=self.employee1).update(
            dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=60))
        params = {
            'employments__dt_from': Converter.convert_date(self.dt_now - timedelta(days=1)),
            'employments__dt_to': Converter.convert_date(self.dt_now - timedelta(days=1)),
        }
        resp = self.client.get(self.get_url('User-list'), data=params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

        params = {
            'employments__dt_from': Converter.convert_date(self.dt_now),
            'employments__dt_to': Converter.convert_date(self.dt_now),
        }
        resp = self.client.get(self.get_url('User-list'), data=params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 8)

        Employment.objects.filter(employee=self.employee2).update(
            dt_hired=self.dt_now + timedelta(days=60), dt_fired=self.dt_now + timedelta(days=90))

        params = {
            'employments__dt_from': Converter.convert_date(self.dt_now + timedelta(days=70)),
            'employments__dt_to': Converter.convert_date(self.dt_now + timedelta(days=70)),
        }
        resp = self.client.get(self.get_url('User-list'), data=params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_distinct_users_with_employment_filters(self):
        params = {
            'employments__dt_from': Converter.convert_date(self.dt_now + timedelta(days=70)),
            'employments__dt_to': Converter.convert_date(self.dt_now + timedelta(days=70)),
        }
        resp = self.client.get(self.get_url('User-list'), data=params)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 8)

    def test_has_biometrics(self):
        UserConnecter.objects.create(
            user=self.user1,
            partner_id='1234',
        )
        response = self.client.get(
            self.get_url('User-list'),
        )
        data = response.json()
        user1 = list(filter(lambda x: x['id'] == self.user1.id, data))[0]
        user2 = list(filter(lambda x: x['id'] == self.user2.id, data))[0]
        self.assertEqual(user1['has_biometrics'], True)
        self.assertEqual(user2['has_biometrics'], False)

    
    def test_delete_biometrics(self):
        self.user1.avatar = 'test/path/avatar.jpg'
        self.user1.save()
        self.assertIsNotNone(self.user1.avatar.url)
        self.assertTrue(bool(self.user1.avatar))
        UserConnecter.objects.create(
            user=self.user1,
            partner_id='1234',
        )
        class TevianMock:
            def delete_person(self, person_id):
                return 200
        with mock.patch.object(recognition, 'Tevian', TevianMock):
            response = self.client.post(
                self.get_url('User-delete-biometrics', pk=self.user1.id),
            )
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data, {'detail': 'Биометрия сотрудника успешно удалена'})
        self.assertEqual(UserConnecter.objects.count(), 0)
        self.user1.refresh_from_db()
        self.assertFalse(bool(self.user1.avatar))

    def test_delete_non_existing_biometrics(self):
        response = self.client.post(
            self.get_url('User-delete-biometrics', pk=self.user1.id),
        )
        data = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(data, {'detail': 'У сотрудника нет биометрии'})

    def test_get_user_with_network_outsourcings(self):
        outsourcing = Network.objects.create(
            name='Аутсорсинг сеть',
            code='1234',
        )
        NetworkConnect.objects.create(
            client=self.network,
            outsourcing=outsourcing,
        )
        resp = self.client.get('/rest_api/auth/user/')
        data = [
            {
                'name': 'Аутсорсинг сеть', 
                'code': '1234', 
                'id': outsourcing.id,
            }
        ]
        self.assertEqual(resp.json()['network']['outsourcings'], data)
        self.assertEqual(resp.json()['network']['clients'], [])
    
    def test_get_user_with_network_clients(self):
        client = Network.objects.create(
            name='Сеть клиента',
            code='1234',
        )
        NetworkConnect.objects.create(
            client=client,
            outsourcing=self.network,
        )
        resp = self.client.get('/rest_api/auth/user/')
        data = [
            {
                'name': 'Сеть клиента', 
                'code': '1234', 
                'id': client.id,
            }
        ]
        self.assertEqual(resp.json()['network']['outsourcings'], [])
        self.assertEqual(resp.json()['network']['clients'], data)

    def test_get_user_with_network_default_stats(self):
        resp = self.client.get('/rest_api/auth/user/')
        data = {
            'timesheet_employee_top': 'fact_total_hours_sum',
            'timesheet_employee_bottom': 'sawh_hours',
            'employee_top': 'work_hours_total',
            'employee_bottom': 'norm_hours_curr_month',
            'day_top': 'covering',
            'day_bottom': 'deadtime',
        }
        self.assertEqual(resp.json()['network']['default_stats'], data)
        data = {
            'timesheet_employee_top': 'main_total_hours_sum',
            'timesheet_employee_bottom': 'norm_hours',
            'employee_top': 'work_days_selected_shop',
            'employee_bottom': 'norm_hours_acc_period',
            'day_top': 'predict_hours',
            'day_bottom': 'graph_hours',
        }
        network = Network.objects.create(
            name='Defaults test',
            settings_values=json.dumps(
                { 
                    'default_stats': data,
                    'show_tabel_graph': False,
                }
            )
        )
        self.user1.network = network
        self.user1.save()
        resp = self.client.get('/rest_api/auth/user/')
        self.assertEqual(resp.json()['network']['default_stats'], data)
        self.assertEqual(resp.json()['network']['show_tabel_graph'], False)
        self.user1.network = self.network
        self.user1.save()

    def test_set_password_as_username_on_user_create(self):
        with self.settings(SET_USER_PASSWORD_AS_LOGIN=True):
            username = "НМ00-123456"
            data = {
                "first_name": " Иван",
                "last_name": " Иванов",
                "middle_name": "Иванович",
                "birthday": "2000-07-20",
                "avatar": "string",
                "phone_number": "string",
                "tabel_code": username,
                "username": username,
                "by_code": True,
            }
            resp = self.client.put(
                self.get_url('User-detail', pk=username), data=self.dump_data(data), content_type='application/json')
            self.assertEqual(resp.status_code, 201)

            user = User.objects.get(username=username)
            self.assertTrue(user.check_password(user.username))

    def test_create_user_with_invalid_email(self):
        username = "НМ00-123456"
        data = {
            "first_name": " Иван",
            "last_name": " Иванов",
            "middle_name": "Иванович",
            "birthday": "2000-07-20",
            "avatar": "string",
            "phone_number": "string",
            "username": username,
            "email": 'invalid@email',
            "by_code": True,
        }
        resp = self.client.put(
            self.get_url('User-detail', pk=username), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)

        user = User.objects.get(username=username)
        self.assertEqual(user.email, '')

    def test_create_user_with_empty_email(self):
        username = 'НМ00-123456'
        data = {
            'username': username,
            'last_name': 'Иванов',
            'first_name': 'Иван',
            'middle_name': 'Иванович',
            'email': '',
            'phone_number': 'string',
            'by_code': True,
        }
        resp = self.client.put(
            self.get_url('User-detail', pk=username), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)

        user = User.objects.get(username=username)
        self.assertEqual(user.email, '')
