from datetime import date, timedelta, datetime, time

from django.test import TestCase

from etc.scripts import fill_calendar
from src.base.tests.factories import (
    NetworkFactory,
    ShopFactory,
    UserFactory,
    EmploymentFactory,
    ShopSettingsFactory,
    WorkerPositionFactory,
    EmployeeFactory,
)
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
        cls.employee = EmployeeFactory(user=cls.user)
        cls.position = WorkerPositionFactory()
        cls.employment = EmploymentFactory(
            shop=cls.shop, employee=cls.employee,
            dt_hired=cls.dt_from - timedelta(days=90), dt_fired=None,
            position=cls.position,
        )
        fill_calendar.fill_days('2020.12.1', '2020.12.31', cls.shop.region.id)

    def setUp(self):
        self.network.refresh_from_db()
        self.position.refresh_from_db()

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
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')

        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 4), type_id='H')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 5), type_id='H')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 6), type_id='S')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 7), type_id='S')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 8), type_id='S')
        stats = self._get_worker_stats()

        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['work_days'],
            {
                'total': 3,
                'selected_shop': 2,
                'other_shops': 1,
            }
        )

        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_days'],
            {
                'total': 2,
                'selected_shop': 2,
                'other_shops': 0,
            }
        )

    def test_work_hours(self):
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type_id='W')
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours'],
            {
                'acc_period': 27.0,
                'other_shops': 9.0,
                'selected_shop': 18.0,
                'total': 27.0,
                'until_acc_period_end': 27.0
            }
        )

    def test_day_type(self):
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 4), type_id='H')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 5), type_id='S')
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['day_type'],
            {
                'W': 3,
                'H': 1,
                'S': 1,
            }
        )

    def test_norm_hours_curr_month(self):
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['norm_hours']['curr_month'],
            183.0,
        )

    def test_overtime_curr_month(self):
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['overtime']['curr_month'],
            -165.0,
        )

    def test_work_hours_for_prev_months_counted_from_fact(self):
        self._set_accounting_period_length(3)
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 10, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 11, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')

        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 10, 1), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')

        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours']['prev_months'],
            18.0
        )
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['work_hours']['prev_months'],
            18.0
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours']['acc_period'],
            27.0
        )
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['work_hours']['acc_period'],
            27.0
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['overtime']['acc_period'],
            -491.0
        )
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['overtime']['acc_period'],
            -491.0
        )

    def test_hours_in_a_week_affect_norm_hours(self):
        self.position.hours_in_a_week = 39
        self.position.save()

        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['norm_hours']['curr_month'],
            178.40000000000003,
        )

    def test_get_hours_sum_and_days_count_by_type(self):
        new_wd_type = self._create_san_day()
        dt = date(2021, 6, 1)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=self.dt_from,
            type_id=new_wd_type.code,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(20)),
        )
        stats = self._get_worker_stats()
        self.assertIn('hours_by_type', stats[self.employee.id]['fact']['approved'])
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['hours_by_type']['SD'],
            9.0,
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['day_type']['SD'],
            1,
        )

    # TODO: после правки констрейнтов раскомментить и проверить, что тест проходит
    # def test_days_count_by_type_for_multiple_wdays_on_one_date(self):
    #     new_wd_type = self._create_san_day()
    #     dt = date(2021, 6, 1)
    #     WorkerDayFactory(
    #         is_approved=True,
    #         is_fact=True,
    #         shop=self.shop,
    #         employment=self.employment,
    #         employee=self.employee,
    #         dt=self.dt_from,
    #         type_id=new_wd_type.code,
    #         dttm_work_start=datetime.combine(dt, time(10)),
    #         dttm_work_end=datetime.combine(dt, time(14)),
    #     )
    #     WorkerDayFactory(
    #         is_approved=True,
    #         is_fact=True,
    #         shop=self.shop,
    #         employment=self.employment,
    #         employee=self.employee,
    #         dt=self.dt_from,
    #         type_id=new_wd_type.code,
    #         dttm_work_start=datetime.combine(dt, time(17)),
    #         dttm_work_end=datetime.combine(dt, time(22)),
    #     )
    #     stats = self._get_worker_stats()
    #     self.assertEqual(
    #         stats[self.employee.id]['fact']['approved']['day_type']['SD'],
    #         1,
    #     )
