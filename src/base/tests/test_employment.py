from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from src.base.models import WorkerPosition, FunctionGroup, Employment, User
from src.timetable.models import WorkTypeName, EmploymentWorkType
from src.util.mixins.tests import TestsHelperMixin


class TestEmploymentAPI(TestsHelperMixin, APITestCase):
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

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def _create_employment(self):
        data = {
            'position_id': self.worker_position.id,
            'dt_hired': (timezone.now() - timedelta(days=500)).strftime('%Y-%m-%d'),
            'shop_id': self.shop.id,
            'user_id': self.user2.id,
        }

        resp = self.client.post(
            self.get_url('Employment-list'), data=self.dump_data(data), content_type='application/json')
        return resp

    def test_work_types_added_on_employment_creation(self):
        resp = self._create_employment()
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        for wtn in [self.wt_name, self.wt_name2]:
            self.assertTrue(EmploymentWorkType.objects.filter(
                employment_id=resp_data['id'],
                work_type__work_type_name=wtn,
            ).exists())

    def test_work_types_updated_on_position_change(self):
        another_worker_position = WorkerPosition.objects.create(
            name='Заместитель директора магазина',
            network=self.network,
        )
        another_wt_name = WorkTypeName.objects.create(name='test_another_name', code='test_another_code')
        another_worker_position.default_work_type_names.add(another_wt_name)
        put_data = {
            'position_id': another_worker_position.id,
            'shop_id': self.shop.id,
            'user_id': self.user2.id,
            'dt_hired': (timezone.now() - timedelta(days=200)).strftime('%Y-%m-%d'),
        }
        self.assertFalse(EmploymentWorkType.objects.filter(employment=self.employment2).exists())
        resp = self.client.put(
            path=self.get_url('Employment-detail', pk=self.employment2.id),
            data=self.dump_data(put_data), content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(EmploymentWorkType.objects.filter(
            employment=self.employment2,
            work_type__work_type_name=another_wt_name,
        ).exists())

    def test_put_create_employment(self):
        """
        change PUT logic of employment for orteka
        :return:
        """

        put_data = {
            'position_id': self.worker_position.id,
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
            'shop_id': self.shop2.id,
            'user_id': self.user2.id,
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk='not_used'),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Employment.objects.filter(
            shop_id=put_data['shop_id'],
            dt_hired=put_data['dt_hired'],
            user_id=put_data['user_id'],
            position_id=put_data['position_id'],
        ).count() == 1)

    def test_put_by_code(self):
        self.shop2.code = str(self.shop2.id)
        self.shop2.save()
        self.user2.username = str(self.user2)
        self.user2.save()

        put_data = {
            'position_code': self.worker_position.code,
            'dt_hired': (timezone.now() - timedelta(days=300)).strftime('%Y-%m-%d'),
            'dt_fired': (timezone.now() + timedelta(days=300)).strftime('%Y-%m-%d'),
            'shop_code': self.shop2.code,
            'username': self.user2.username,
            'by_code': True,
        }

        resp = self.client.put(
            path=self.get_url('Employment-detail', pk='not_used'),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)  # created
        self.assertTrue(Employment.objects.filter(
            shop_id=self.shop2.id,
            dt_hired=put_data['dt_hired'],
            dt_fired=put_data['dt_fired'],
            user_id=self.user2.id,
            position_id=self.worker_position.id,
        ).count() == 1)

        put_data['dt_fired'] = timezone.now().strftime('%Y-%m-%d')
        resp = self.client.put(
            path=self.get_url('Employment-detail', pk='not_used'),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)  # updated
        self.assertTrue(Employment.objects.filter(
            shop_id=self.shop2.id,
            dt_hired=put_data['dt_hired'],
            dt_fired=put_data['dt_fired'],
            user_id=self.user2.id,
            position_id=self.worker_position.id,
        ).count() == 1)

    def test_auto_timetable(self):
        employment_ids = list(Employment.objects.filter(shop=self.shop).values_list('id', flat=True))
        employment_ids = employment_ids[1:-2]

        self.assertEqual(Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=True).count(), 4)
        data = {
            "employment_ids": employment_ids,
            "auto_timetable": False,
        }
        response = self.client.post('/rest_api/employment/auto_timetable/', data=self.dump_data(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=False).count(), 2)
        self.assertEqual(list(Employment.objects.get_active(self.network, shop=self.shop, auto_timetable=False).values_list('id', flat=True)), employment_ids)
