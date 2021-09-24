from datetime import date, time, datetime, timedelta
from decimal import Decimal

from django.test import override_settings, TestCase

from etc.scripts import fill_calendar
from src.base.models import (
    Network,
    SAWHSettings,
    SAWHSettingsMapping,
    ProductionDay,
)
from src.base.tests.factories import (
    NetworkFactory,
    UserFactory,
    ShopFactory,
    EmploymentFactory,
    GroupFactory,
    WorkerPositionFactory,
    EmployeeFactory,
    RegionFactory,
)
from src.timetable.models import WorkerDay, Timesheet
from src.timetable.tests.factories import WorkerDayFactory
from src.timetable.timesheet.tasks import calc_timesheets
from src.timetable.timesheet.utils import get_timesheet_stats
from src.timetable.worker_day.stat import (
    WorkersStatsGetter,
)
from src.util.mixins.tests import TestsHelperMixin


class SawhSettingsHelperMixin(TestsHelperMixin):
    acc_period = None

    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(
            accounting_period_length=cls.acc_period,
        )
        cls.region = RegionFactory()
        cls.shop = ShopFactory(
            region=cls.region,
            network=cls.network,
            tm_open_dict='{"all": "08:00:00"}',
            tm_close_dict='{"all": "22:00:00"}',
        )
        cls.group = GroupFactory(network=cls.network)
        cls.worker_position = WorkerPositionFactory(group=cls.group)
        cls.worker = UserFactory(network=cls.network)
        cls.employee = EmployeeFactory(user=cls.worker)
        cls.employment = EmploymentFactory(
            dt_hired='2001-01-01', dt_fired='3999-12-12',
            employee=cls.employee, shop=cls.shop, position=cls.worker_position)
        cls.dt = date(2021, 1, 1)
        cls.add_group_perm(cls.group, 'ShopSchedule', 'GET')
        cls.add_group_perm(cls.group, 'ShopSchedule', 'PUT')

        cls.sawh_settings, _sawh_settings_created = SAWHSettings.objects.update_or_create(
            network=cls.network,
            work_hours_by_months={f'm{month_num}': 1 / cls.network.accounting_period_length for month_num in
                                  range(1, 12 + 1)}
        )
        cls.sawh_settings_mapping = SAWHSettingsMapping.objects.create(
            year=2021,
            sawh_settings=cls.sawh_settings,
        )
        cls.sawh_settings_mapping.shops.add(cls.shop)

        fill_calendar.fill_days('2021.01.01', '2021.12.31', cls.shop.region_id)

    def setUp(self):
        self.network.refresh_from_db()
        self.sawh_settings.refresh_from_db()
        self.shop.refresh_from_db()
        self.worker_position.refresh_from_db()
        self.employment.refresh_from_db()

    def _set_obj_data(self, obj, **data):
        for i, v in data.items():
            setattr(obj, i, v)
        obj.save(update_fields=list(data.keys()))

    def _set_network_settings(self, **data):
        self._set_obj_data(self.network, **data)

    def _test_hours_for_period(
            self, dt_from, dt_to, expected_norm_hours, hours_k='sawh_hours', plan_fact_k='plan',
            approved_k='approved', period_k='selected_period'):
        workers_stats_getter = WorkersStatsGetter(
            employee_id=self.employee.id,
            shop_id=self.shop.id,
            dt_from=dt_from,
            dt_to=dt_to,
        )
        workers_stats = workers_stats_getter.run()
        norm_hours = workers_stats[self.employee.id][plan_fact_k][approved_k][hours_k][period_k]
        self.assertEqual(norm_hours, expected_norm_hours)
        return norm_hours

    def _test_hours_for_acc_period(self, dt, expected_norm_hours, **kwargs):
        dt_from, dt_to = self.network.get_acc_period_range(dt)
        self._test_hours_for_period(dt_from=dt_from, dt_to=dt_to, expected_norm_hours=expected_norm_hours, **kwargs)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWHSettingsMonthAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_MONTH

    def test_norm_hours_for_acc_period(self):
        self._test_hours_for_acc_period(dt=date(2021, 1, 1), expected_norm_hours=120.0)
        self._test_hours_for_acc_period(dt=date(2021, 2, 1), expected_norm_hours=151.0)
        self._test_hours_for_acc_period(dt=date(2021, 3, 1), expected_norm_hours=176.0)
        self._test_hours_for_acc_period(dt=date(2021, 4, 1), expected_norm_hours=175.0)
        self._test_hours_for_acc_period(dt=date(2021, 5, 1), expected_norm_hours=152.0)
        self._test_hours_for_acc_period(dt=date(2021, 6, 1), expected_norm_hours=167.0)
        self._test_hours_for_acc_period(dt=date(2021, 7, 1), expected_norm_hours=176.0)
        self._test_hours_for_acc_period(dt=date(2021, 8, 1), expected_norm_hours=176.0)
        self._test_hours_for_acc_period(dt=date(2021, 9, 1), expected_norm_hours=176.0)
        self._test_hours_for_acc_period(dt=date(2021, 10, 1), expected_norm_hours=168.0)
        self._test_hours_for_acc_period(dt=date(2021, 11, 1), expected_norm_hours=159.0)
        self._test_hours_for_acc_period(dt=date(2021, 12, 1), expected_norm_hours=176.0)

    def test_norm_for_36_hours_week(self):
        self.worker_position.hours_in_a_week = 36
        self.worker_position.save()
        self._test_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_norm_hours=135.8,
        )

    def test_subtract_sick_days_from_norm_hours_exact(self):
        # часть новогодн. праздников
        for day_num in range(1, 5):
            WorkerDayFactory(
                employee=self.employee,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        # выходные
        for day_num in range(30, 32):
            WorkerDayFactory(
                employee=self.employee,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        self._test_hours_for_acc_period(
            dt=date(2021, 1, 1), expected_norm_hours=120.0, hours_k='norm_hours', period_k='acc_period')

        # рабочая неделя
        for day_num in range(25, 30):
            WorkerDayFactory(
                employee=self.employee,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        self._test_hours_for_acc_period(
            dt=date(2021, 1, 1), expected_norm_hours=80.0, hours_k='norm_hours', period_k='acc_period')

    def test_subtract_sick_days_from_norm_hours_mean(self):
        # часть новогодн. праздников
        for day_num in range(1, 5):
            WorkerDayFactory(
                employee=self.employee,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        self._test_hours_for_acc_period(
            dt=date(2021, 1, 1),
            expected_norm_hours=104.51612903225806,
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWHSettingsQuarterAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_QUARTER

    def test_norm_hours_for_acc_period(self):
        self._test_hours_for_acc_period(dt=date(2021, 1, 1), expected_norm_hours=447.0)
        self._test_hours_for_acc_period(dt=date(2021, 4, 1), expected_norm_hours=494.0)
        self._test_hours_for_acc_period(dt=date(2021, 7, 1), expected_norm_hours=528.0)
        self._test_hours_for_acc_period(dt=date(2021, 10, 1), expected_norm_hours=503.0)

    def test_equal_distribution_by_months(self):
        self.sawh_settings.work_hours_by_months = {
            f'm{month_num}': 1 for month_num in range(1, 12 + 1)}
        self.sawh_settings.save(update_fields=['work_hours_by_months'])

        self._test_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_norm_hours=149,
        )
        self._test_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_norm_hours=149
        )
        self._test_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_norm_hours=149
        )

    def test_two_employments_case_one(self):
        self.sawh_settings.work_hours_by_months['m1'] = 0.3125
        self.sawh_settings.work_hours_by_months['m2'] = 0.375
        self.sawh_settings.work_hours_by_months['m3'] = 0.3125
        self.sawh_settings.save()
        self.employment.dt_hired = '2021-01-01'
        self.employment.dt_fired = '2021-02-09'
        self.employment.save()
        worker_position2 = WorkerPositionFactory(network=self.network)
        sawh_settings2 = SAWHSettings.objects.create(
            network=self.network,
            work_hours_by_months={
              'm1': 0.3125,
              'm2': 0.3125,
              'm3': 0.375,
            },
        )
        sawh_settings_mapping2 = SAWHSettingsMapping.objects.create(
            sawh_settings=sawh_settings2,
            priority=10,
        )
        sawh_settings_mapping2.positions.add(worker_position2)
        EmploymentFactory(
            dt_hired='2021-02-10', dt_fired='3999-12-12',
            employee=self.employee, shop=self.shop, position=worker_position2)
        res = self._test_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_norm_hours=127.01030927835052,
        )
        res2 = self._test_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_norm_hours=146.87942456195367,
        )
        res3 = self._test_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_norm_hours=173.1102661596958,
        )
        self.assertEqual(res + res2 + res3, 447)

    def test_two_employments_case_two(self):
        self.sawh_settings.work_hours_by_months['m1'] = 0.3
        self.sawh_settings.work_hours_by_months['m2'] = 0.3
        self.sawh_settings.work_hours_by_months['m3'] = 0.4
        self.sawh_settings.save()
        self.employment.dt_hired = '2021-01-01'
        self.employment.dt_fired = '2021-02-09'
        self.employment.save()
        worker_position2 = WorkerPositionFactory(network=self.network)
        sawh_settings2 = SAWHSettings.objects.create(
            network=self.network,
            work_hours_by_months={
              'm1': 0.3125,
              'm2': 0.375,
              'm3': 0.3125,
            },
        )
        sawh_settings_mapping2 = SAWHSettingsMapping.objects.create(
            sawh_settings=sawh_settings2,
            priority=10,
        )
        sawh_settings_mapping2.positions.add(worker_position2)
        EmploymentFactory(
            dt_hired='2021-02-10', dt_fired='2021-03-20',
            employee=self.employee, shop=self.shop, position=worker_position2)
        res = self._test_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_norm_hours=133.1891891891892,
        )
        res2 = self._test_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_norm_hours=158.3046535642052,
        )
        res3 = self._test_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_norm_hours=91.50615724660561,
        )
        self.assertEqual(res + res2 + res3, 383.0)

    def test_fixed_sawh_settings_type(self):
        self.sawh_settings.work_hours_by_months = {
            'm1': 170,
            'm2': 180,
        }
        self.sawh_settings.type = SAWHSettings.FIXED_HOURS
        self.sawh_settings.save()
        res = self._test_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_norm_hours=170,
        )
        res2 = self._test_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_norm_hours=180,
        )
        res3 = self._test_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_norm_hours=176,  # по умолчанию часы из произв. календаря
        )
        self.assertEqual(res + res2 + res3, 526)

    def test_fixed_sawh_settings_type_with_additional_employment_with_zero_norm_work_hours(self):
        EmploymentFactory(
            dt_hired='2021-01-01', dt_fired='2021-01-31',
            employee=self.employee, shop=self.shop, position=WorkerPositionFactory(group=self.group),
            norm_work_hours=0,
        )

        self.sawh_settings.work_hours_by_months = {
            'm1': 170,
            'm2': 180,
        }
        self.sawh_settings.type = SAWHSettings.FIXED_HOURS
        self.sawh_settings.save()
        res = self._test_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_norm_hours=170,
        )
        res2 = self._test_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_norm_hours=180,
        )
        res3 = self._test_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_norm_hours=176,  # по умолчанию часы из произв. календаря
        )
        self.assertEqual(res + res2 + res3, 526)

    def test_override_region_prod_cal(self):
        self.sawh_settings_mapping.shops.remove(self.shop)
        subregion = RegionFactory(parent=self.region, name='Подрегион', code='subregion')
        ProductionDay.objects.create(region=subregion, dt=date(2021, 2, 10), type=ProductionDay.TYPE_HOLIDAY)
        self.shop.region = subregion
        self.shop.save(update_fields=['region'])
        self._test_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_norm_hours=143,
        )

    @override_settings(FISCAL_SHEET_DIVIDER_ALIAS='nahodka')
    def test_correct_norm_hours_last_month_acc_period(self):
        self.sawh_settings_mapping.shops.remove(self.shop)
        self._test_hours_for_period(
            dt_from=date(2021, 7, 1),
            dt_to=date(2021, 7, 31),
            expected_norm_hours=176,
        )
        self._test_hours_for_period(
            dt_from=date(2021, 8, 1),
            dt_to=date(2021, 8, 31),
            expected_norm_hours=176,
        )
        self._test_hours_for_period(
            dt_from=date(2021, 9, 1),
            dt_to=date(2021, 9, 30),
            expected_norm_hours=176,
        )
        wdays = (
            ((WorkerDay.TYPE_HOLIDAY, None, None), (
                date(2021, 7, 3),
                date(2021, 7, 5),
                date(2021, 7, 6),
                date(2021, 7, 7),
                date(2021, 7, 11),
                date(2021, 7, 14),
                date(2021, 7, 15),
                date(2021, 7, 18),
                date(2021, 7, 19),
                date(2021, 7, 22),
                date(2021, 7, 23),
                date(2021, 7, 26),
                date(2021, 7, 27),

                date(2021, 8, 3),
                date(2021, 8, 4),
                date(2021, 8, 7),
                date(2021, 8, 8),
                date(2021, 8, 12),

                date(2021, 9, 1),
                date(2021, 9, 2),
                date(2021, 9, 4),
                date(2021, 9, 5),
                date(2021, 9, 8),
                date(2021, 9, 9),
                date(2021, 9, 13),
                date(2021, 9, 20),
                date(2021, 9, 21),
                date(2021, 9, 24),
                date(2021, 9, 28),
                date(2021, 9, 29),
            )),
            ((WorkerDay.TYPE_VACATION, None, None), (
                date(2021, 8, 16),
                date(2021, 8, 17),
                date(2021, 8, 18),
                date(2021, 8, 19),
                date(2021, 8, 20),
                date(2021, 8, 21),
                date(2021, 8, 22),
                date(2021, 8, 23),
                date(2021, 8, 24),
                date(2021, 8, 25),
                date(2021, 8, 26),
                date(2021, 8, 27),
                date(2021, 8, 28),
                date(2021, 8, 29),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(8), time(21)), (
                date(2021, 7, 1),
                date(2021, 7, 2),
                date(2021, 7, 4),
                date(2021, 7, 8),
                date(2021, 7, 12),
                date(2021, 7, 13),
                date(2021, 7, 16),
                date(2021, 7, 17),
                date(2021, 7, 20),
                date(2021, 7, 21),
                date(2021, 7, 24),
                date(2021, 7, 29),

                date(2021, 8, 1),
                date(2021, 8, 2),
                date(2021, 8, 5),
                date(2021, 8, 6),
                date(2021, 8, 9),
                date(2021, 8, 14),
                date(2021, 8, 15),
                date(2021, 8, 30),
                date(2021, 8, 31),

                date(2021, 9, 3),
                date(2021, 9, 6),
                date(2021, 9, 7),
                date(2021, 9, 10),
                date(2021, 9, 11),
                date(2021, 9, 12),
                date(2021, 9, 14),
                date(2021, 9, 15),
                date(2021, 9, 16),
                date(2021, 9, 17),
                date(2021, 9, 19),
                date(2021, 9, 22),
                date(2021, 9, 23),
                date(2021, 9, 25),
                date(2021, 9, 26),
                date(2021, 9, 27),
                date(2021, 9, 30),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(8), time(1, 15)), (
                date(2021, 7, 9),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(10), time(21)), (
                date(2021, 7, 10),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(14, 6), time(21)), (
                date(2021, 7, 25),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(8), time(22)), (
                date(2021, 7, 28),

                date(2021, 8, 10),

                date(2021, 9, 18),
            )),

            ((WorkerDay.TYPE_WORKDAY, time(20), time(8)), (
                date(2021, 8, 11),
            )),
        )
        for (wd_type_id, tm_start, tm_end), dates in wdays:
            for dt in dates:
                is_night_work = False
                if tm_start and tm_end and tm_end < tm_start:
                    is_night_work = True

                is_work_day = wd_type_id == WorkerDay.TYPE_WORKDAY
                WorkerDayFactory(
                    type=wd_type_id,
                    dt=dt,
                    shop=self.shop,
                    employee=self.employee,
                    employment=self.employment,
                    dttm_work_start=datetime.combine(dt, tm_start) if is_work_day else None,
                    dttm_work_end=datetime.combine(dt + timedelta(days=1) if is_night_work else dt,
                                                   tm_end) if is_work_day else None,
                    is_fact=is_work_day,
                    is_approved=True,
                )

        self._test_hours_for_period(
            dt_from=date(2021, 7, 1),
            dt_to=date(2021, 7, 31),
            expected_norm_hours=176,
        )

        calc_timesheets(employee_id__in=[self.employee.id], dt_from=date(2021, 7, 1), dt_to=date(2021, 7, 31))

        timesheet_qs = Timesheet.objects.filter(
            employee=self.employee,
            dt__gte=date(2021, 7, 1),
            dt__lte=date(2021, 7, 31),
        )
        timesheet_stats = get_timesheet_stats(
            filtered_qs=timesheet_qs,
            dt_from=date(2021, 7, 1),
            dt_to=date(2021, 7, 31),
            user=self.worker,
        )
        self.assertEqual(timesheet_stats[self.employee.id]['main_total_hours_sum'], 176)
        self.assertEqual(timesheet_stats[self.employee.id]['sawh_hours'], 176)

        subregion = RegionFactory(parent=self.region, name='Татарстан', code='tatarstan')
        self.shop.region = subregion
        self.shop.save(update_fields=['region'])
        ProductionDay.objects.create(
            region=subregion, dt=date(2021, 7, 19), type=ProductionDay.TYPE_SHORT_WORK)
        ProductionDay.objects.create(
            region=subregion, dt=date(2021, 7, 20), type=ProductionDay.TYPE_HOLIDAY, is_celebration=True)
        ProductionDay.objects.create(
            region=subregion, dt=date(2021, 8, 30), type=ProductionDay.TYPE_HOLIDAY, is_celebration=True)

        timesheet_qs = Timesheet.objects.filter(
            employee=self.employee,
            dt__gte=date(2021, 7, 1),
            dt__lte=date(2021, 7, 31),
        )
        timesheet_stats = get_timesheet_stats(
            filtered_qs=timesheet_qs,
            dt_from=date(2021, 7, 1),
            dt_to=date(2021, 7, 31),
            user=self.worker,
        )
        self.assertEqual(timesheet_stats[self.employee.id]['main_total_hours_sum'], 176)
        self.assertEqual(timesheet_stats[self.employee.id]['sawh_hours'], 167)

        self._test_hours_for_period(
            dt_from=date(2021, 7, 1),
            dt_to=date(2021, 7, 31),
            expected_norm_hours=167,
        )
        self._test_hours_for_period(
            dt_from=date(2021, 8, 1),
            dt_to=date(2021, 8, 31),
            expected_norm_hours=92.12903225806451,
        )
        self._test_hours_for_period(
            dt_from=date(2021, 9, 1),
            dt_to=date(2021, 9, 30),
            expected_norm_hours=176,
        )

        calc_timesheets(employee_id__in=[self.employee.id], dt_from=date(2021, 8, 1), dt_to=date(2021, 8, 31))
        calc_timesheets(employee_id__in=[self.employee.id], dt_from=date(2021, 9, 1), dt_to=date(2021, 9, 30))

        timesheet_qs = Timesheet.objects.filter(
            employee=self.employee,
            dt__gte=date(2021, 9, 1),
            dt__lte=date(2021, 9, 30),
        )
        timesheet_stats = get_timesheet_stats(
            filtered_qs=timesheet_qs,
            dt_from=date(2021, 9, 1),
            dt_to=date(2021, 9, 30),
            user=self.worker,
        )
        self.assertEqual(timesheet_stats[self.employee.id]['main_total_hours_sum'], 176)
        self.assertEqual(timesheet_stats[self.employee.id]['sawh_hours'], 176)

        self.network.correct_norm_hours_last_month_acc_period = True
        self.network.prev_months_work_hours_source = Network.MAIN_TIMESHEET
        self.network.save()

        calc_timesheets(employee_id__in=[self.employee.id], dt_from=date(2021, 9, 1), dt_to=date(2021, 9, 30))
        timesheet_qs = Timesheet.objects.filter(
            employee=self.employee,
            dt__gte=date(2021, 9, 1),
            dt__lte=date(2021, 9, 30),
        )
        timesheet_stats = get_timesheet_stats(
            filtered_qs=timesheet_qs,
            dt_from=date(2021, 9, 1),
            dt_to=date(2021, 9, 30),
            user=self.worker,
        )
        self.assertEqual(timesheet_stats[self.employee.id]['main_total_hours_sum'], Decimal('162.87'))
        self.assertEqual(timesheet_stats[self.employee.id]['sawh_hours'], 162.87)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWHSettingsHalfYearAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_HALF_YEAR

    def test_norm_hours_for_acc_period(self):
        self._test_hours_for_acc_period(
            dt=date(2021, 1, 1),
            expected_norm_hours=941.0000000000001,
        )
        self._test_hours_for_acc_period(
            dt=date(2021, 7, 1),
            expected_norm_hours=1031.0,
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWHSettingsYearAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_YEAR

    def test_norm_hours_for_acc_period(self):
        self._test_hours_for_acc_period(
            dt=date(2021, 1, 1),
            expected_norm_hours=1971.9999999999993,
        )
