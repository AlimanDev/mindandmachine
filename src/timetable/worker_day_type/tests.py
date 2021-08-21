from rest_framework.test import APITestCase

from src.base.tests.factories import UserFactory, EmploymentFactory, EmployeeFactory, ShopFactory, GroupFactory
from src.util.mixins.tests import TestsHelperMixin
from ..models import WorkerDayType


class TestWorkerDayTypeViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        cls.employee = EmployeeFactory(user=cls.user)
        cls.shop = ShopFactory()
        cls.group = GroupFactory()
        cls.employment = EmploymentFactory(employee=cls.employee, shop=cls.shop, function_group=cls.group)
        cls.add_group_perm(cls.group, 'WorkerDayType', 'GET')

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user)

    def _get_wd_types(self, extra_data=None):
        data = {}
        if extra_data:
            data.update(extra_data)
        resp = self.client.get(
            path=self.get_url('WorkerDayType-list'),
            data=data,
        )
        return resp

    def test_get_worker_day_types(self):
        resp = self._get_wd_types()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 11)

        WorkerDayType.objects.create(
            code='SD',
            name='Санитарный день',
            short_name='C/Д',
            html_color='#f7f7f7',
            use_in_plan=True,
            use_in_fact=True,
            excel_load_code='СД',
            is_dayoff=False,
            is_work_hours=False,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=True,
            show_stat_in_hours=True,
            ordering=0,
        )

        resp = self._get_wd_types()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 12)
