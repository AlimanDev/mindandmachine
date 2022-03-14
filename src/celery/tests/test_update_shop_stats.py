import datetime

from django.test import TestCase, override_settings
from django.utils import timezone

from src.timetable.shop_month_stat.tasks import (
    update_shop_stats,
)
from src.forecast.models import (
    OperationType,
    OperationTypeName,
    PeriodClients,
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
        cls.work_type_name = WorkTypeName.objects.create(name='Кассы', code='test', network=cls.network)
        cls.work_type = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name)

        cls.operation_type = OperationType.objects.get(shop=cls.shop, work_type=cls.work_type)
        for day in range(2):
            dt = timezone.now() + datetime.timedelta(days=day)
            for tm in range(24):
                if 10 < tm < 20:
                    PeriodClients.objects.create(
                        dttm_forecast=datetime.datetime.combine(dt, datetime.time(tm)),
                        value=2.0,
                        operation_type=cls.operation_type,
                    )

    @override_settings(UPDATE_SHOP_STATS_WORK_TYPES_CODES=['test'])
    def test_update_shop_status(self):
        self.assertEqual(ShopMonthStat.objects.count(), 0)
        update_shop_stats()
        self.assertEqual(ShopMonthStat.objects.count(), 3)
        shop_stat = ShopMonthStat.objects.get(shop=self.shop, dt=timezone.now().replace(day=1))
        self.assertIsNotNone(shop_stat.fot)
        self.assertIsNotNone(shop_stat.predict_needs)
