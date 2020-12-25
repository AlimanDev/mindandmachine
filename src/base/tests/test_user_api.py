from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from src.base.models import WorkerPosition, Employment, User
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
            "tabel_code": username,
            "username": username,
            "by_code": True,
        }
        resp = self.client.put(self.get_url('User-detail', pk=username), data=data)
        self.assertEqual(resp.status_code, 201)

        user = User.objects.filter(username=username).first()
        self.assertEqual(user.email, '')

        data['email'] = 'email@example.com'
        resp = self.client.put(self.get_url('User-detail', pk=username), data=data)
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, 'email@example.com')

    def test_create_user_with_post(self):
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
        resp = self.client.put(self.get_url('User-detail', pk=username), data=data)
        self.assertEqual(resp.status_code, 201)

    def test_get_list(self):
        resp = self.client.get(self.get_url('User-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 8)

    def test_get_users_only_with_active_employment(self):
        Employment.objects.exclude(user=self.user1).update(
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

        Employment.objects.filter(user=self.user2).update(
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
