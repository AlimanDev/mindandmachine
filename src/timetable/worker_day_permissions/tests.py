from rest_framework.test import APITestCase

from src.timetable.models import WorkerDayPermission, WorkerDay
from src.util.mixins.tests import TestsHelperMixin


class TestWorkerDayPermissions(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user1)

    def _get_wd_perms(self, extra_data=None):
        data = {'shop': self.shop2.id}
        if extra_data:
            data.update(extra_data)
        resp = self.client.get(
            path=self.get_url('worker_day_permissions'),
            data=data,
        )
        return resp

    def test_get_worker_day_permissions(self):
        resp = self._get_wd_perms()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 66)

    def test_filter_worker_day_permissions_by_action(self):
        resp = self._get_wd_perms(extra_data={'action': WorkerDayPermission.CREATE_OR_UPDATE})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            all(wdp['worker_day_permission']['action'] == WorkerDayPermission.CREATE_OR_UPDATE for wdp in resp.json()))
        self.assertEqual(len(resp.json()), len(WorkerDay.TYPES_USED) * len(WorkerDayPermission.GRAPH_TYPES))

    def test_filter_worker_day_permissions_by_graph_type(self):
        resp = self._get_wd_perms(extra_data={'graph_type': WorkerDayPermission.FACT})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            all(wdp['worker_day_permission']['graph_type'] == WorkerDayPermission.FACT for wdp in resp.json()))
        self.assertEqual(len(resp.json()), len(WorkerDay.TYPES_USED) * len(WorkerDayPermission.ACTIONS))
