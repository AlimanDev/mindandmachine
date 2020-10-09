import datetime

from django.test import TestCase, override_settings

from src.celery.tasks import (
    update_shop_stats,
)
from src.timetable.models import (
    ShopMonthStat,
    WorkTypeName,
    WorkType,
)
from src.util.mixins.tests import TestsHelperMixin


class TestUpdateShopStats(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.work_type_name = WorkTypeName.objects.create(name='Тест', code='test')
        cls.work_type = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name)

    @override_settings(UPDATE_SHOP_STATS_WORK_TYPES_CODES=['test'])
    def test_update_shop_status(self):
        self.assertEqual(ShopMonthStat.objects.count(), 0)
        update_shop_stats()
        self.assertEqual(ShopMonthStat.objects.count(), 3)
        shop_stat = ShopMonthStat.objects.get(shop=self.shop, dt=datetime.datetime.now().replace(day=1))
        self.assertEqual(shop_stat.fot, 880)
        self.assertEqual(shop_stat.lack, 0)  # на самом деле покрытие
        self.assertEqual(shop_stat.idle, 0)
