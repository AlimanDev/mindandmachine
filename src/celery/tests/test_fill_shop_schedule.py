from datetime import datetime, timedelta, time

from django.test import TestCase

from src.base.models import ShopSchedule
from src.base.tests.factories import NetworkFactory, ShopFactory, UserFactory
from src.base.shop.tasks import fill_shop_schedule
from src.util.mixins.tests import TestsHelperMixin


class TestFillShopScheduleTask(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.user = UserFactory(network=cls.network)
        cls.shop = ShopFactory(
            network=cls.network,
            tm_open_dict='{"0": "08:00:00","1": "08:00:00","2": "08:00:00","3": "08:00:00","4": "08:00:00"}',
            tm_close_dict='{"0": "20:00:00","1": "20:00:00","2": "20:00:00","3": "20:00:00","4": "19:00:00"}',
        )
        cls.dt = datetime(2021, 1, 1)

    def test_fill_standard_schedule(self):
        self.assertEqual(ShopSchedule.objects.count(), 0)
        fill_shop_schedule(self.shop.id, self.dt, 31)
        self.assertEqual(ShopSchedule.objects.filter(type='W').count(), 21)
        self.assertEqual(ShopSchedule.objects.filter(type='H').count(), 10)
        schedule = ShopSchedule.objects.filter(
            dt=self.dt,
            shop=self.shop,
        ).first()
        self.assertEqual(schedule.type, 'W')
        self.assertEqual(schedule.opens, time(8))
        self.assertEqual(schedule.closes, time(19))

        schedule = ShopSchedule.objects.filter(
            dt=self.dt + timedelta(days=1),
            shop=self.shop,
        ).first()
        self.assertEqual(schedule.type, 'H')
        self.assertEqual(schedule.opens, None)
        self.assertEqual(schedule.closes, None)

    def test_nonstandard_schedule_not_overwritten(self):
        ShopSchedule.objects.create(
            dt=self.dt,
            shop=self.shop,
            type='H',
            opens=None,
            closes=None,
            modified_by=self.user,
        )
        fill_shop_schedule(self.shop.id, self.dt, 31)
        self.assertEqual(ShopSchedule.objects.filter(type='W').count(), 20)
        self.assertEqual(ShopSchedule.objects.filter(type='H').count(), 11)
        schedule = ShopSchedule.objects.filter(
            dt=self.dt,
            shop=self.shop,
        ).first()
        self.assertEqual(schedule.type, 'H')
        self.assertEqual(schedule.opens, None)
        self.assertEqual(schedule.closes, None)
