from datetime import date, timedelta, datetime, time
from unittest import expectedFailure, mock

from django.core.cache import cache
from django.db import transaction
from django.test import TestCase

from etc.scripts import fill_calendar
from src.base.models import ProductionDay, Region
from src.base.tests.factories import (
    NetworkFactory,
    ShopFactory,
    UserFactory,
    EmploymentFactory,
    ShopSettingsFactory,
    WorkerPositionFactory,
    EmployeeFactory,
)
from src.timetable.models import WorkerDay, WorkerDayType
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
        cache.clear()

    def _set_accounting_period_length(self, length):
        self.network.accounting_period_length = length
        self.network.save(update_fields=('accounting_period_length',))

    def _get_worker_stats(self, dt_from=None, dt_to=None):
        return WorkersStatsGetter(
            dt_from=dt_from or self.dt_from,
            dt_to=dt_to or self.dt_to,
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
            dttm_work_start=datetime.combine(self.dt_from, time(10)),
            dttm_work_end=datetime.combine(self.dt_from, time(20)),
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

    @expectedFailure
    def test_days_count_by_type_for_multiple_wdays_on_one_date(self):
        dt = date(2021, 6, 1)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=self.dt_from,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_from, time(10)),
            dttm_work_end=datetime.combine(self.dt_from, time(14)),
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=self.dt_from,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_from, time(17)),
            dttm_work_end=datetime.combine(self.dt_from, time(22)),
        )
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['day_type'][WorkerDay.TYPE_WORKDAY],
            1,  # TODO: логичней ведь, чтобы была 1 если 2 дня на 1 дату?
        )

    def test_wd_types_with_is_work_hours_false_not_counted_in_work_hours_sum(self):
        """
        Проверка, что типы дней с is_work_hours=False не учитываются в сумме "Рабочих часов"
        """
        san_day = self._create_san_day()
        dt_now = date.today()
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=dt_now,
            type=san_day,
            dttm_work_start=datetime.combine(dt_now, time(10)),
            dttm_work_end=datetime.combine(dt_now, time(20)),
        )
        stats = self._get_worker_stats(dt_from=dt_now, dt_to=dt_now)
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours']['total'],
            0,
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['overtime']['curr_month'],
            0,
        )

    def _test_cache(self, call_count, called_with=[], resp_count=2):

        def _data_for_employee(e):
            return [
                {
                    'employee_id': e,
                    'employment_id': self.employments[e],
                    'dt__month': self.dt_from.month,
                    'period_start': self.dt_from,
                    'period_end': self.dt_to,
                    'has_vacation_or_sick_plan_approved': False,
                    'vacation_or_sick_plan_approved_count': 0,
                    'vacation_or_sick_plan_approved_count_selected_period': 0,
                    'has_vacation_or_sick_plan_not_approved': False,
                    'vacation_or_sick_plan_not_approved_count': 0,
                    'vacation_or_sick_plan_not_approved_count_selected_period': 0,
                    'norm_hours_acc_period': 156,
                    'norm_hours_prev_months': 156,
                    'norm_hours_curr_month': 156,
                    'norm_hours_curr_month_end': 156,
                    'norm_hours_selected_period': 156,
                    'empl_days_count': 20,
                    'empl_days_count_selected_period': 20,
                    'empl_days_count_outside_of_selected_period': 20,
                }
            ]
        
        mock_prod_call = mock.MagicMock(side_effect=_data_for_employee)

        with mock.patch.object(WorkersStatsGetter, '_get_prod_cal_for_employee', mock_prod_call):
            stat = self._get_worker_stats()
            self.assertEqual(len(stat), resp_count)
            self.assertEqual(mock_prod_call.call_count, call_count)
            if called_with:
                calls = [mock.call(call) for call in called_with]
                mock_prod_call.assert_has_calls(calls, any_order=True)

    def test_cache(self):
        self.user2 = UserFactory()
        self.employee2 = EmployeeFactory(user=self.user2)
        self.employment2 = EmploymentFactory(
            shop=self.shop, employee=self.employee2,
            dt_hired=self.dt_from - timedelta(days=90), dt_fired=None,
            position=self.position,
        )
        self.employments = {
            employment.employee_id: employment.id
            for employment in [self.employment, self.employment2]
        }
        
        self._test_cache(2, [self.employee.id, self.employee2.id])
        self._test_cache(0)

        self.position.hours_in_a_week = 39
        self.position.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        self.position.ordering = 2
        self.position.save()
        self._test_cache(0)

        p_day, _ = ProductionDay.objects.update_or_create(dt=self.dt_from, region=self.shop.region, defaults={'type': ProductionDay.TYPE_WORK})
        self._test_cache(2, [self.employee.id, self.employee2.id])

        p_day.type = ProductionDay.TYPE_HOLIDAY
        p_day.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        w_type = WorkerDayType.objects.get(code=WorkerDay.TYPE_VACATION)
        w_type.is_reduce_norm = False
        w_type.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        w_type.is_dayoff = False
        w_type.save()
        self._test_cache(0)
        
        self.network.accounting_period_length = 12
        self.network.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            region2 = Region.objects.create(name='Татарстан')
            self.shop.region = region2
            self.shop.save()
            self._test_cache(2, [self.employee.id, self.employee2.id])

            self.employment2.norm_work_hours = 90
            self.employment2.save()
            self._test_cache(1, [self.employee2.id])

            self.employment2.dt_hired = self.dt_from - timedelta(days=95)
            self.employment2.save()
            self._test_cache(1, [self.employee2.id])

            self.employment2.dt_fired = self.dt_to + timedelta(days=60)
            self.employment2.save()
            self._test_cache(1, [self.employee2.id])

            w_type.is_reduce_norm = True
            w_type.is_dayoff = True
            w_type.save()
            self._test_cache(2, [self.employee.id, self.employee2.id])

            wd = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=w_type,
                dt=self.dt_from,
                dttm_work_start=None,
                dttm_work_end=None,
            )
            self._test_cache(1, [self.employee2.id])

            wd.save()
            self._test_cache(1, [self.employee2.id])

            wd.delete()
            self._test_cache(1, [self.employee2.id])

            wd2 = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type_id=WorkerDay.TYPE_HOLIDAY,
                dt=self.dt_from + timedelta(1),
                dttm_work_start=None,
                dttm_work_end=None,
            )
            self._test_cache(0)

            wd2.save()
            self._test_cache(0)

            wd2.delete()
            self._test_cache(0)

            self.employment2.delete()
            self._test_cache(0, resp_count=1)
            self.assertIsNone(cache.get(f'prod_cal_{self.dt_from}_{self.dt_to}_{self.employee2.id}'))
