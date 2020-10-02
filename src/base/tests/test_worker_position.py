from rest_framework.test import APITestCase

from src.base.models import WorkerPosition, FunctionGroup
from src.timetable.models import WorkTypeName
from src.util.mixins.tests import TestsHelperMixin


class TestWorkerPositionAPI(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        WorkerPosition.objects.bulk_create(
            [
                WorkerPosition(
                    name=name,
                    network=cls.network,
                )
                for name in ['Директор магазина', 'Продавец', 'Продавец-кассир', 'ЗДМ']
            ]
        )
        cls.worker_position = WorkerPosition.objects.last()
        cls.worker_positions_count = 4
        cls.wt_name = WorkTypeName.objects.create(name='test_name', code='test_code')
        cls.wt_name2 = WorkTypeName.objects.create(name='test_name2', code='test_code2')

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_list(self):
        resp = self.client.get(self.get_url('WorkerPosition-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), self.worker_positions_count)

    def test_create(self):
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='WorkerPosition',
            level_up=1,
            level_down=99,
        )

        data = {
            'name': 'test_name',
            'network_id': self.network.id,
            'code': 'test_code',
        }

        resp = self.client.post(
            self.get_url('WorkerPosition-list'), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            WorkerPosition.objects.filter(dttm_deleted__isnull=True).count(), self.worker_positions_count + 1)

    def test_retrieve(self):
        resp = self.client.get(self.get_url('WorkerPosition-detail', pk=self.worker_position.id))
        self.assertEqual(resp.status_code, 200)

    def test_put(self):
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='WorkerPosition',
            level_up=1,
            level_down=99,
        )

        put_data = {
            'name': 'test_name',
            'network_id': self.network.id,
            'code': 'test_code',
        }
        resp = self.client.put(
            path=self.get_url('WorkerPosition-detail', pk=self.worker_position.id),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

    def test_delete(self):
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='DELETE',
            func='WorkerPosition',
            level_up=1,
            level_down=99,
        )

        resp = self.client.delete(path=self.get_url('WorkerPosition-detail', pk=self.worker_position.id))
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(
            WorkerPosition.objects.filter(dttm_deleted__isnull=True).count(), self.worker_positions_count - 1)
