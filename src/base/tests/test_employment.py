from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from src.base.models import WorkerPosition, FunctionGroup
from src.timetable.models import WorkTypeName, EmploymentWorkType
from src.util.mixins.tests import APITestsHelperMixin


class TestEmploymentAPI(APITestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.worker_position = WorkerPosition.objects.create(
            name='Директор магазина',
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
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='Employment',
            level_up=1,
            level_down=99,
        )

        resp = self._create_employment()
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        for wtn in [self.wt_name, self.wt_name2]:
            self.assertTrue(EmploymentWorkType.objects.filter(
                employment_id=resp_data['id'],
                work_type__work_type_name=wtn,
            ).exists())

    def test_work_types_updated_on_position_change(self):
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='Employment',
            level_up=1,
            level_down=99,
        )

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
