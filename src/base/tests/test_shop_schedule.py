from datetime import timedelta, datetime

from django.test import override_settings
from rest_framework.test import APITestCase

from src.base.models import ShopSchedule
from src.base.tests.factories import (
    NetworkFactory,
    ShopFactory,
    UserFactory,
    EmploymentFactory,
    GroupFactory,
    EmployeeFactory,
)
from src.celery.tasks import fill_shop_schedule
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestShopScheduleViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.user = UserFactory(network=cls.network)
        cls.shop = ShopFactory(
            network=cls.network,
            tm_open_dict='{"0": "08:00:00","1": "08:00:00","2": "08:00:00","3": "08:00:00","4": "08:00:00"}',
            tm_close_dict='{"0": "20:00:00","1": "20:00:00","2": "20:00:00","3": "20:00:00","4": "19:00:00"}',
        )
        cls.group = GroupFactory(network=cls.network)
        cls.employee = EmployeeFactory(user=cls.user)
        cls.employment = EmploymentFactory(
            employee=cls.employee, shop=cls.shop, function_group=cls.group)
        cls.dt = datetime(2021, 1, 1)
        fill_shop_schedule(cls.shop.id, cls.dt, 31)
        cls.add_group_perm(cls.group, 'ShopSchedule', 'GET')
        cls.add_group_perm(cls.group, 'ShopSchedule', 'PUT')

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.shop.refresh_from_db()

    def test_list(self):
        resp = self.client.get(
            path=self.get_url('ShopSchedule-list', department_pk=self.shop.id),
            data=dict(
                dt__gte=Converter.convert_date(self.dt),
                dt__lte=Converter.convert_date(self.dt + timedelta(days=30)),
            )
        )
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 31)
        self.assertEqual(resp_data[0]['type'], 'W')
        self.assertEqual(resp_data[1]['type'], 'H')
        self.assertEqual(resp_data[2]['type'], 'H')

    def test_put(self):
        resp = self.client.put(
            path=self.get_url('ShopSchedule-detail', department_pk=self.shop.id, dt=Converter.convert_date(self.dt)),
            data=self.dump_data({
                "type": "H",
                "opens": None,
                "closes": None
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        schedule = ShopSchedule.objects.filter(
            shop=self.shop,
            dt=self.dt,
        ).first()
        self.assertEqual(schedule.type, 'H')
        self.assertEqual(schedule.opens, None)
        self.assertEqual(schedule.closes, None)
