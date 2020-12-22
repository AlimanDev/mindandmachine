from datetime import date, timedelta

from django.test import TestCase

from etc.scripts import fill_calendar
from src.base.tests.factories import NetworkFactory, ShopFactory, UserFactory, EmploymentFactory, ShopSettingsFactory
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from .stat import WorkersStatsGetter


class TestWorkersStatsGetter(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt_from = date(2020, 12, 1)
        cls.dt_to = date(2020, 12, 31)
        cls.network = NetworkFactory(crop_work_hours_by_shop_schedule=False)
        cls.shop_settings = ShopSettingsFactory(
            breaks__value='[[0, 2040, [60]]]')
        cls.shop = ShopFactory(settings=cls.shop_settings)
        cls.shop2 = ShopFactory(settings=cls.shop_settings)
        cls.user = UserFactory()
        cls.employment = EmploymentFactory(
            shop=cls.shop, user=cls.user,
            dt_hired=cls.dt_from - timedelta(days=90), dt_fired=None,
        )
        fill_calendar.fill_days('2020.12.1', '2020.12.31', cls.shop.region.id)

    def setUp(self):
        self.network.refresh_from_db()

    def _set_accounting_period_length(self, length):
        self.network.accounting_period_length = length
        self.network.save(update_fields=('accounting_period_length',))

    def _get_worker_stats(self):
        return WorkersStatsGetter(
            dt_from=self.dt_from,
            dt_to=self.dt_to,
            shop_id=self.shop.id,
        ).run()

    def test_work_days_count(self):
        WorkerDayFactory(is_fact=True, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type='W')
        WorkerDayFactory(is_fact=True, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type='W')

        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type='W')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type='W')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type='W')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 4), type='H')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 5), type='H')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 6), type='S')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 7), type='S')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 8), type='S')
        stats = self._get_worker_stats()

        self.assertDictEqual(
            stats[str(self.user.id)]['plan']['approved']['work_days'],
            {
                'total': 3,
                'selected_shop': 2,
                'other_shops': 1,
            }
        )

        self.assertDictEqual(
            stats[str(self.user.id)]['fact']['approved']['work_days'],
            {
                'total': 2,
                'selected_shop': 2,
                'other_shops': 0,
            }
        )

    def test_work_hours(self):
        WorkerDayFactory(is_fact=True, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type='W')
        WorkerDayFactory(is_fact=True, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type='W')
        WorkerDayFactory(is_fact=True, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type='W')
        stats = self._get_worker_stats()
        self.assertDictEqual(
            stats[str(self.user.id)]['fact']['approved']['work_hours'],
            {
                'total': 27.0,
                'selected_shop': 18.0,
                'other_shops': 9.0,
            }
        )

    def test_day_type(self):
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type='W')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type='W')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type='W')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 4), type='H')
        WorkerDayFactory(is_fact=False, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 5), type='S')
        stats = self._get_worker_stats()
        self.assertDictEqual(
            stats[str(self.user.id)]['plan']['approved']['day_type'],
            {
                'W': 3,
                'H': 1,
                'S': 1,
            }
        )

    def test_norm_hours_curr_month(self):
        stats = self._get_worker_stats()
        self.assertDictEqual(
            stats[str(self.user.id)]['plan']['approved']['norm_hours_curr_month'],
            {
                'value': 183.0,
            }
        )

    def test_overtime_curr_month(self):
        WorkerDayFactory(is_fact=True, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type='W')
        WorkerDayFactory(is_fact=True, is_approved=True, worker=self.user, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type='W')
        stats = self._get_worker_stats()
        self.assertDictEqual(
            stats[str(self.user.id)]['fact']['approved']['overtime_curr_month'],
            {
                'value': -165.0,
            }
        )
