from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import expectedFailure

import pandas as pd
from django.db.models import Sum, Q
from django.test import TestCase, override_settings

from src.base.models import (
    SAWHSettings,
    SAWHSettingsMapping,
    Network,
    WorkerPosition,
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftScheduleInterval,
)
from src.base.tests.factories import (
    ShopFactory,
    UserFactory,
    EmploymentFactory,
    EmployeeFactory,
    WorkerPositionFactory,
)
from src.timetable.models import (
    WorkerDay,
    WorkType,
    WorkTypeName,
    TimesheetItem,
    WorkerDayType,
)
from src.timetable.tests.factories import WorkerDayFactory
from ._base import TestTimesheetMixin


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS='nahodka')
class TestNahodkaDivider(TestTimesheetMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def test_48h_week_rest(self):
        self._calc_timesheets()
        self.assertEqual(TimesheetItem.objects.count(), 62)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, day_type_id='W').count(), 7)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, day_type_id='W').count(), 5)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, day_hours__gt=0).count(), 2)

    def test_12h_threshold(self):
        dt = date(2021, 6, 14)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(7)),
            dttm_work_end=datetime.combine(dt, time(22)),
        )
        self._calc_timesheets()
        self.assertEqual(TimesheetItem.objects.filter(
            dt=dt, employee=self.employee_worker,
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
        ).aggregate(total_hours_sum=Sum('day_hours') + Sum('night_hours'))['total_hours_sum'], Decimal('14.00'))
        self.assertEqual(TimesheetItem.objects.filter(
            dt=dt, employee=self.employee_worker,
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
        ).aggregate(total_hours_sum=Sum('day_hours') + Sum('night_hours'))['total_hours_sum'], Decimal('12.00'))
        self.assertEqual(TimesheetItem.objects.filter(
            dt=dt, employee=self.employee_worker,
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
        ).aggregate(total_hours_sum=Sum('day_hours') + Sum('night_hours'))['total_hours_sum'], Decimal('2.00'))

    def test_overtime_more_than_zero(self):
        WorkerDay.objects.all().delete()
        date_ranges = (
            (1, 4),
            (7, 11),
            (14, 18),
            (21, 25),
        )
        for date_range in date_ranges:
            for dt in pd.date_range(date(2021, 6, date_range[0]), date(2021, 6, date_range[1])).date:
                WorkerDayFactory(
                    is_approved=True,
                    is_fact=True,
                    shop=self.shop,
                    employment=self.employment_worker,
                    employee=self.employee_worker,
                    dt=dt,
                    type_id=WorkerDay.TYPE_WORKDAY,
                    dttm_work_start=datetime.combine(dt, time(10)),
                    dttm_work_end=datetime.combine(dt, time(21)),
                )

        self._calc_timesheets()
        fact_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        main_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        additional_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(fact_timesheet_hours['total_hours_sum'], 190)
        self.assertEqual(main_timesheet_hours['total_hours_sum'], 167)
        self.assertEqual(additional_timesheet_hours['total_hours_sum'], 23)

    def test_overtime_less_than_zero_after_48h_rest_moves(self):
        """
        В случае когда переработки < 0
        Например когда часть дней ушла в доп. табель при проверке не непрерывный 48ч отдых

        В данном тесте переноса часов в осн. табель из доп. не будет,
        т.к. все дни, где будут часы в доп. табеле это выходные дни в осн. табеле
        """
        WorkerDay.objects.all().delete()
        for dt in pd.date_range(date(2021, 6, 7), date(2021, 6, 27)).date:
            WorkerDayFactory(
                is_approved=True,
                is_fact=True,
                shop=self.shop,
                employment=self.employment_worker,
                employee=self.employee_worker,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(21)),
            )

        self._calc_timesheets()
        fact_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        main_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        additional_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(fact_timesheet_hours['total_hours_sum'], 210)
        self.assertEqual(main_timesheet_hours['total_hours_sum'], 150)
        self.assertEqual(additional_timesheet_hours['total_hours_sum'], 60)

    def test_overtime_less_than_zero_after_12h_threshold_moves(self):
        """
        В случае когда переработки < 0
        Например когда часть часов ушла в доп. табель при проверке не превышение рабочих часов в день 12ч
        """
        WorkerDay.objects.all().delete()
        date_ranges = (
            (1, 4),
            (7, 11),
            (14, 17),
        )
        for date_range in date_ranges:
            for dt in pd.date_range(date(2021, 6, date_range[0]), date(2021, 6, date_range[1])).date:
                WorkerDayFactory(
                    is_approved=True,
                    is_fact=True,
                    shop=self.shop,
                    employment=self.employment_worker,
                    employee=self.employee_worker,
                    dt=dt,
                    type_id=WorkerDay.TYPE_WORKDAY,
                    dttm_work_start=datetime.combine(dt, time(8)),
                    dttm_work_end=datetime.combine(dt, time(22)),
                )

        self._calc_timesheets()
        fact_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        main_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        additional_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(fact_timesheet_hours['total_hours_sum'], 169)
        self.assertEqual(main_timesheet_hours['total_hours_sum'], 156)
        self.assertEqual(additional_timesheet_hours['total_hours_sum'], 13)

    def test_wd_types_with_is_work_hours_false_not_divided_on_main_and_additional_timesheet(self):
        WorkerDay.objects.all().delete()
        san_day = self._create_san_day()
        date_ranges = (
            ((1, 4), san_day.code,),
            ((7, 11), WorkerDay.TYPE_WORKDAY),
            ((14, 17), WorkerDay.TYPE_WORKDAY),
        )
        for date_range, wd_type_id in date_ranges:
            for dt in pd.date_range(date(2021, 6, date_range[0]), date(2021, 6, date_range[1])).date:
                WorkerDayFactory(
                    is_approved=True,
                    is_fact=True,
                    shop=self.shop,
                    employment=self.employment_worker,
                    employee=self.employee_worker,
                    dt=dt,
                    type_id=wd_type_id,
                    dttm_work_start=datetime.combine(dt, time(8)),
                    dttm_work_end=datetime.combine(dt, time(22)),
                )

        self._calc_timesheets()
        fact_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
        ).aggregate(
            all_hours_sum=Sum('day_hours') + Sum('night_hours'),
            work_hours_sum=Sum('day_hours', filter=Q(day_type__is_work_hours=True))
                           + Sum('night_hours', filter=Q(day_type__is_work_hours=True)),
        )
        main_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        additional_timesheet_hours = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(fact_timesheet_hours['all_hours_sum'], 169)
        self.assertEqual(fact_timesheet_hours['work_hours_sum'], 117)
        self.assertEqual(main_timesheet_hours['total_hours_sum'], 108)
        self.assertEqual(additional_timesheet_hours['total_hours_sum'], 9)  # ушло в доп. по кол-ву часов в сутках > 12

    def test_vacation_moved_to_main_timesheet(self):
        WorkerDay.objects.all().delete()
        date_ranges = (
            ((1, 2), WorkerDay.TYPE_VACATION),
        )
        for date_range, wd_type_id in date_ranges:
            for dt in pd.date_range(date(2021, 6, date_range[0]), date(2021, 6, date_range[1])).date:
                WorkerDayFactory(
                    is_approved=True,
                    is_fact=False,
                    shop=self.shop,
                    employment=self.employment_worker,
                    employee=self.employee_worker,
                    dt=dt,
                    type_id=wd_type_id,
                )

        self._calc_timesheets()
        timesheet = TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, employee=self.employee_worker, dt=date(2021, 6, 1))
        self.assertEqual(timesheet.day_type_id, WorkerDay.TYPE_VACATION)

    def test_calc_timesheet_with_start_time_only(self):
        WorkerDay.objects.all().delete()
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dttm_work_start=datetime(2021, 6, 1, 9, 45),
            dttm_work_end=None,
            dt=date(2021, 6, 1),
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
                                                      day_type_id=WorkerDay.TYPE_WORKDAY).count(), 0)

    @expectedFailure
    def test_make_holiday_in_prev_months(self):
        WorkerDay.objects.all().delete()
        date_ranges = (
            ((1, 3, 10), WorkerDay.TYPE_WORKDAY),
            ((27, 27, 9), WorkerDay.TYPE_HOLIDAY),
            ((28, 30, 9), WorkerDay.TYPE_WORKDAY),
        )
        for date_range, wd_type_id in date_ranges:
            for dt in pd.date_range(date(2021, date_range[2], date_range[0]),
                                    date(2021, date_range[2], date_range[1])).date:
                WorkerDayFactory(
                    is_approved=True,
                    is_fact=True,
                    shop=self.shop,
                    employment=self.employment_worker,
                    employee=self.employee_worker,
                    dt=dt,
                    type_id=wd_type_id,
                    dttm_work_start=datetime.combine(dt, time(8)),
                    dttm_work_end=datetime.combine(dt, time(22)),
                )

        self._calc_timesheets(dt_from=date(2021, 9, 1), dt_to=date(2021, 9, 30))
        self._calc_timesheets(dt_from=date(2021, 10, 1), dt_to=date(2021, 10, 31))
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
                                                      dt='2021-10-01').get().day_type_id, WorkerDay.TYPE_WORKDAY)
        # TODO: какое желаемое поведение в данном случае? -- один из вариантов:
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
                                                      dt='2021-10-02').get().day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
                                                      dt='2021-10-03').get().day_type_id, WorkerDay.TYPE_HOLIDAY)

    def test_shop_and_position_set_for_system_holidays(self):
        WorkerDay.objects.all().delete()

        self._calc_timesheets(dt_from=date(2021, 10, 1), dt_to=date(2021, 10, 31))
        main_ts_item = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-10-01').get()
        self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertIsNotNone(main_ts_item.position_id)
        self.assertIsNotNone(main_ts_item.shop_id)


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS='pobeda', TIMESHEET_MIN_HOURS_THRESHOLD=Decimal('5.00'))
class TestPobedaDivider(TestTimesheetMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.network.round_work_hours_alg = Network.ROUND_TO_HALF_AN_HOUR
        cls.network.save()
        cls.san_day = cls._create_san_day()
        sawh_settings = SAWHSettings.objects.create(
            network=cls.network,
            work_hours_by_months={
                'm6': 175,
            },
            type=SAWHSettings.FIXED_HOURS,
        )
        sawh_settings_mapping = SAWHSettingsMapping.objects.create(
            sawh_settings=sawh_settings,
            year=2021,
        )
        sawh_settings_mapping.positions.add(cls.position_worker)
        WorkerDayType.objects.filter(
            code__in=[WorkerDay.TYPE_VACATION, WorkerDay.TYPE_MATERNITY]
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS,
        )
        WorkerDayType.objects.filter(
            code__in=[WorkerDay.TYPE_ABSENSE],
        ).update(
            is_work_hours=True,
        )
        WorkerDayType.objects.filter(
            code__in=[WorkerDay.TYPE_SICK],
        ).update(
            is_work_hours=True,
            get_work_hours_method=WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL,
        )

    def test_calc_timesheets(self):
        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT).count(), 30)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN).count(), 30)

    def test_work_in_other_shop_moved_to_additional_timesheet(self):
        another_shop = ShopFactory(
            parent=self.root_shop,
            name='SHOP_NAME2',
            network=self.network,
            email='shop2@example.com',
            settings__breaks=self.breaks,
        )
        WorkerDay.objects.filter(
            is_approved=True,
            is_fact=True,
            dt=date(2021, 6, 7),
            employee=self.employee_worker,
        ).update(
            shop=another_shop,
        )
        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt=date(2021, 6, 7)).count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=date(2021, 6, 7)).count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=date(2021, 6, 7)).get().day_type_id,
                         WorkerDay.TYPE_HOLIDAY)

    def test_other_position_work_moved_to_additional_timesheet(self):
        self.network.get_position_from_work_type_name_in_calc_timesheet = True
        self.network.save()
        other_position = WorkerPosition.objects.create(
            network=self.network,
            name='Работник',
            group=self.group_worker,
        )
        other_work_type_name = WorkTypeName.objects.create(
            position=other_position,
            network=self.network,
            name='other',
            code='other',
        )
        other_work_type = WorkType.objects.create(
            work_type_name=other_work_type_name,
            shop=self.shop,
        )
        dt = date(2021, 6, 7)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(20)),
            dttm_work_end=datetime.combine(dt, time(23)),
            cashbox_details__work_type=other_work_type,
        )
        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, day_type_id=WorkerDay.TYPE_WORKDAY).count(), 3)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=date(2021, 6, 7)).count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=date(2021, 6, 7)).get().day_type_id,
                         WorkerDay.TYPE_WORKDAY)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=date(2021, 6, 7)).get().position_id,
                         self.employment_worker.position_id)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt=date(2021, 6, 7),
            position=other_position).count(), 1)

    def test_vacation_and_sick_hours_divide(self):
        WorkerDay.objects.all().delete()
        wdays = (
            ((WorkerDay.TYPE_HOLIDAY, None, None, None), (
                date(2021, 6, 2),
                date(2021, 6, 3),
            )),
            ((WorkerDay.TYPE_SICK, None, None, timedelta(hours=12)), (
                date(2021, 6, 18),
                date(2021, 6, 19),
            )),
            ((WorkerDay.TYPE_VACATION, None, None, None), (
                date(2021, 6, 6),
                date(2021, 6, 7),
                date(2021, 6, 8),
                date(2021, 6, 9),
                date(2021, 6, 10),
                date(2021, 6, 11),
                date(2021, 6, 12),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(8), time(21), None), (
                date(2021, 6, 1),
                date(2021, 6, 4),
                date(2021, 6, 5),
                date(2021, 6, 13),
                date(2021, 6, 14),
                date(2021, 6, 15),
                date(2021, 6, 16),
                date(2021, 6, 17),
                date(2021, 6, 20),
                date(2021, 6, 21),
                date(2021, 6, 22),
                date(2021, 6, 23),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(8), time(18), None), (
                date(2021, 6, 24),
            )),
        )
        for (wd_type_id, tm_start, tm_end, work_hours), dates in wdays:
            for dt in dates:
                is_night_work = False
                if tm_start and tm_end and tm_end < tm_start:
                    is_night_work = True

                is_work_day = wd_type_id == WorkerDay.TYPE_WORKDAY
                WorkerDayFactory(
                    type_id=wd_type_id,
                    dt=dt,
                    shop=self.shop,
                    employee=self.employee_worker,
                    employment=self.employment_worker,
                    dttm_work_start=datetime.combine(dt, tm_start) if is_work_day else None,
                    dttm_work_end=datetime.combine(dt + timedelta(days=1) if is_night_work else dt,
                                                   tm_end) if is_work_day else None,
                    is_fact=is_work_day,
                    is_approved=True,
                    work_hours=work_hours,
                )

        data = WorkerDay.objects.filter(type__is_work_hours=True).aggregate(work_hours_sum=Sum('work_hours'))
        self.assertEqual(data['work_hours_sum'].total_seconds() / 3600, 219)
        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-12').day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-13').day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-06').day_hours, 7)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-18').day_type_id, WorkerDay.TYPE_ABSENSE)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-18').day_hours, 12)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-19').day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt='2021-06-19').first(), None)

    def test_divide_workday_and_vacation(self):
        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL
        vacation_type.is_work_hours = True
        vacation_type.is_dayoff = True
        vacation_type.save()
        vacation_type.allowed_additional_types.add(workday_type)

        WorkerDay.objects.all().delete()
        dt = date(2021, 6, 7)
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            work_hours=timedelta(hours=10),
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(22)),
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(8)),
            dttm_work_end=datetime.combine(dt, time(22)),
        )
        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, dt=dt).count(), 2)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=dt).day_type_id, WorkerDay.TYPE_VACATION)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt=dt).day_type_id, WorkerDay.TYPE_WORKDAY)

    def test_divide_weekend_at_the_junction_of_calendar_weeks(self):
        WorkerDay.objects.all().delete()
        wdays = (
            ((WorkerDay.TYPE_HOLIDAY, None, None, None), (
                date(2021, 6, 6),
                date(2021, 6, 7),
                date(2021, 6, 13),
                date(2021, 6, 14),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(8), time(21), None), (
                date(2021, 6, 1),
                date(2021, 6, 2),
                date(2021, 6, 3),
                date(2021, 6, 4),
                date(2021, 6, 5),
                date(2021, 6, 8),
                date(2021, 6, 9),
                date(2021, 6, 10),
                date(2021, 6, 11),
                date(2021, 6, 12),
                date(2021, 6, 15),
                date(2021, 6, 16),
                date(2021, 6, 17),
                date(2021, 6, 18),
                date(2021, 6, 19),
                date(2021, 6, 20),
            )),
        )
        for (wd_type_id, tm_start, tm_end, work_hours), dates in wdays:
            for dt in dates:
                is_night_work = False
                if tm_start and tm_end and tm_end < tm_start:
                    is_night_work = True

                is_work_day = wd_type_id == WorkerDay.TYPE_WORKDAY
                WorkerDayFactory(
                    type_id=wd_type_id,
                    dt=dt,
                    shop=self.shop,
                    employee=self.employee_worker,
                    employment=self.employment_worker,
                    dttm_work_start=datetime.combine(dt, tm_start) if is_work_day else None,
                    dttm_work_end=datetime.combine(dt + timedelta(days=1) if is_night_work else dt,
                                                   tm_end) if is_work_day else None,
                    is_fact=is_work_day,
                    is_approved=True,
                    work_hours=work_hours,
                )

        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-06').day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-07').day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-08').day_type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-13').day_type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-14').day_type_id, WorkerDay.TYPE_HOLIDAY)

        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-15').day_type_id, WorkerDay.TYPE_HOLIDAY)
        for day_num in range(16, 21):
            self.assertEqual(TimesheetItem.objects.get(
                timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt=date(2021, 6, day_num)).day_type_id,
                             WorkerDay.TYPE_WORKDAY)

    def test_vacation_dont_moved_to_additional_timesheet(self):
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS
        vacation_type.is_work_hours = True
        vacation_type.is_dayoff = True
        vacation_type.save()

        WorkerDay.objects.all().delete()
        wdays = (
            ((WorkerDay.TYPE_VACATION, None, None, None), (
                date(2021, 6, 3),
                date(2021, 6, 4),
                date(2021, 6, 5),
            )),
            ((WorkerDay.TYPE_WORKDAY, time(8), time(21), None), (
                date(2021, 6, 1),
                date(2021, 6, 2),
                date(2021, 6, 6),
                date(2021, 6, 7),
                date(2021, 6, 8),
                date(2021, 6, 9),
                date(2021, 6, 10),
                date(2021, 6, 11),
                date(2021, 6, 12),
                date(2021, 6, 13),
                date(2021, 6, 14),
                date(2021, 6, 15),
                date(2021, 6, 16),
                date(2021, 6, 17),
                date(2021, 6, 20),
                date(2021, 6, 21),
                date(2021, 6, 22),
                date(2021, 6, 23),
                date(2021, 6, 25),
                date(2021, 6, 26),
                date(2021, 6, 27),
                date(2021, 6, 28),
            )),
        )
        for (wd_type_id, tm_start, tm_end, work_hours), dates in wdays:
            for dt in dates:
                is_night_work = False
                if tm_start and tm_end and tm_end < tm_start:
                    is_night_work = True

                is_work_day = wd_type_id == WorkerDay.TYPE_WORKDAY
                WorkerDayFactory(
                    type_id=wd_type_id,
                    dt=dt,
                    shop=self.shop,
                    employee=self.employee_worker,
                    employment=self.employment_worker,
                    dttm_work_start=datetime.combine(dt, tm_start) if is_work_day else None,
                    dttm_work_end=datetime.combine(dt + timedelta(days=1) if is_night_work else dt,
                                                   tm_end) if is_work_day else None,
                    is_fact=is_work_day,
                    is_approved=True,
                    work_hours=work_hours,
                )

        data = WorkerDay.objects.filter(type__is_work_hours=True).aggregate(work_hours_sum=Sum('work_hours'))
        self.assertEqual(data['work_hours_sum'].total_seconds() / 3600, 282.0)
        self._calc_timesheets(reraise_exc=True)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-03').day_type_id, WorkerDay.TYPE_VACATION)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-04').day_type_id, WorkerDay.TYPE_VACATION)
        self.assertEqual(TimesheetItem.objects.get(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN, dt='2021-06-05').day_type_id, WorkerDay.TYPE_VACATION)

        self.assertIsNone(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt='2021-06-03').first())
        self.assertIsNone(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt='2021-06-04').first())
        self.assertIsNone(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt='2021-06-05').first())


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS='shift_schedule')
class TestShiftScheduleDivider(TestTimesheetMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        sawh_settings = SAWHSettings.objects.create(
            network=cls.network,
            work_hours_by_months={},
            type=SAWHSettings.SHIFT_SCHEDULE,
        )
        sawh_settings_mapping = SAWHSettingsMapping.objects.create(
            sawh_settings=sawh_settings,
            year=2021,
        )
        sawh_settings_mapping.positions.add(cls.position_worker)
        # 7-13 июня рабочие дни по плановому графику
        # 12,13 выходные
        cls.shift_schedule = ShiftSchedule.objects.create(
            network=cls.network,
            name='График смен',
        )
        cls.shift_schedule_interval = ShiftScheduleInterval.objects.create(
            shift_schedule=cls.shift_schedule,
            employee=cls.employee_worker,
            dt_start=date(2021, 6, 1),
            dt_end=date(2021, 6, 30),
        )
        for dt in pd.date_range(date(2021, 6, 7), date(2021, 6, 11)).date:
            ShiftScheduleDay.objects.create(
                dt=dt, shift_schedule=cls.shift_schedule, day_type_id=WorkerDay.TYPE_WORKDAY,
                work_hours=Decimal("8.00"),
                day_hours=Decimal("8.00"),
                night_hours=Decimal("0.00"))
        for dt in pd.date_range(date(2021, 6, 12), date(2021, 6, 13)).date:
            ShiftScheduleDay.objects.create(
                dt=dt, shift_schedule=cls.shift_schedule, day_type_id=WorkerDay.TYPE_HOLIDAY, work_hours=Decimal("0.00"))

        cls.user_worker2 = UserFactory(email='worker2@example.com', network=cls.network)
        cls.employee_worker2 = EmployeeFactory(user=cls.user_worker2)
        cls.position_worker2 = WorkerPositionFactory(
            name='Работник', group=cls.group_worker,
            breaks=cls.breaks,
        )
        cls.employment_worker2 = EmploymentFactory(
            employee=cls.employee_worker2, shop=cls.shop, position=cls.position_worker2,
        )
        cls.work_type_name_worker2 = WorkTypeName.objects.create(
            position=cls.position_worker2,
            network=cls.network,
            name='worker2',
            code='worker2',
        )
        cls.work_type_worker2 = WorkType.objects.create(
            work_type_name=cls.work_type_name_worker2,
            shop=cls.shop,
        )

        for dt in pd.date_range(date(2021, 6, 7), date(2021, 6, 13)).date:
            WorkerDayFactory(
                is_approved=True,
                is_fact=True,
                shop=cls.shop,
                employment=cls.employment_worker2,
                employee=cls.employee_worker2,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(20)),
                cashbox_details__work_type=cls.work_type_worker2,
            )
            WorkerDayFactory(
                is_approved=True,
                is_fact=False,
                shop=cls.shop,
                employment=cls.employment_worker2,
                employee=cls.employee_worker2,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(20)),
                cashbox_details__work_type=cls.work_type_worker2,
            )
        cls.individual_shift_schedule = ShiftSchedule.objects.create(
            network=cls.network,
            name='Индивидуальный график смен',
            employee=cls.employee_worker2,
        )
        for dt in pd.date_range(date(2021, 6, 7), date(2021, 6, 11)).date:
            ShiftScheduleDay.objects.create(
                dt=dt, shift_schedule=cls.individual_shift_schedule, day_type_id=WorkerDay.TYPE_WORKDAY,
                work_hours=Decimal("8.00"))
        for dt in pd.date_range(date(2021, 6, 12), date(2021, 6, 13)).date:
            ShiftScheduleDay.objects.create(
                dt=dt, shift_schedule=cls.individual_shift_schedule, day_type_id=WorkerDay.TYPE_HOLIDAY, work_hours=Decimal("0.00"))

    def test_plan_schedule_hours_gt_shift_schedule_hours(self):
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True)
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=date(2021, 6, 7), timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=date(2021, 6, 7), timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)
            self.assertEqual(main_ts_item.day_hours, 8)
            self.assertEqual(additional_ts_item.day_hours, 1)

    def test_plan_schedule_hours_lt_shift_schedule_hours(self):
        for employee in [self.employee_worker]:
            ShiftScheduleDay.objects.filter(work_hours__gt=0).update(work_hours=Decimal("14"))

            self._calc_timesheets(employee_id=employee.id, reraise_exc=True)
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=date(2021, 6, 7), timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee,
                dt=date(2021, 6, 7), timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 9)
            self.assertIsNone(additional_ts_item)

    def test_plan_schedule_is_workday_and_shift_schedule_is_holiday(self):
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True)
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=date(2021, 6, 12), timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=date(2021, 6, 12), timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 0)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_HOLIDAY)
            self.assertEqual(additional_ts_item.day_hours, 9)
            self.assertEqual(additional_ts_item.day_type_id, WorkerDay.TYPE_WORKDAY)

    def test_absence_plan_schedule_is_workday_and_shift_schedule_is_holiday(self):
        WorkerDay.objects.filter(is_fact=True).delete()
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=date(2021, 6, 12), timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=date(2021, 6, 12), timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 0)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_HOLIDAY)
            self.assertIsNone(additional_ts_item)

    def test_absence_plan_schedule_is_workday_and_shift_schedule_is_workday(self):
        WorkerDay.objects.filter(is_fact=True).delete()
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=date(2021, 6, 7), timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=date(2021, 6, 7), timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 0)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_ABSENSE)
            self.assertIsNone(additional_ts_item)

    def test_plan_schedule_is_vacation_and_shift_schedule_is_workday(self):
        dt = date(2021, 6, 7)
        WorkerDay.objects.filter(is_fact=False, dt=dt).update(
            type_id=WorkerDay.TYPE_VACATION,
            dttm_work_start=None,
            dttm_work_end=None,
            work_hours=timedelta(0),
        )
        WorkerDay.objects.filter(is_fact=True, dt=dt).delete()
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 0)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_VACATION)
            self.assertIsNone(additional_ts_item)

    def test_plan_schedule_is_vacation_and_shift_schedule_is_holiday(self):
        dt = date(2021, 6, 12)
        WorkerDay.objects.filter(is_fact=False, dt=dt).update(
            type_id=WorkerDay.TYPE_VACATION,
            dttm_work_start=None,
            dttm_work_end=None,
            work_hours=timedelta(0),
        )
        WorkerDay.objects.filter(is_fact=True, dt=dt).delete()
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 0)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_VACATION)  # или должен быть выходной?
            self.assertIsNone(additional_ts_item)

    def test_workday_and_vacation_plan_schedule_and_shift_schedule_is_holiday(self):
        dt = date(2021, 6, 12)
        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.allowed_additional_types.add(workday_type)
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker2,
            employee=self.employee_worker2,
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
        )
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 0)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_VACATION)
            self.assertIsNotNone(additional_ts_item)
            self.assertEqual(additional_ts_item.day_hours, 9)

    def test_workday_and_vacation_plan_schedule_and_shift_schedule_is_workday(self):
        dt = date(2021, 6, 7)
        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.allowed_additional_types.add(workday_type)
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker2,
            employee=self.employee_worker2,
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
        )

        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 0)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_VACATION)
            self.assertIsNotNone(additional_ts_item)
            self.assertEqual(additional_ts_item.day_hours, 9)

    def test_work_hours_moved_from_additional_tabel_to_main_if_main_less_than_norm(self):
        dt = date(2021, 6, 11)
        dt_donors = [date(2021, 6, 7), date(2021, 6, 8), date(2021, 6, 9)]
        for wd in WorkerDay.objects.filter(dt=dt, is_fact=True):
            wd.dttm_work_start = datetime.combine(dt, time(10))
            wd.dttm_work_end = datetime.combine(dt, time(16))
            wd.save()
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_hours, 8)
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_WORKDAY)
            self.assertIsNone(additional_ts_item)

            for dt_donor in dt_donors:
                donor_additional_ts_item = TimesheetItem.objects.filter(
                    employee=employee, dt=dt_donor, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
                self.assertIsNone(donor_additional_ts_item)

    def test_work_hours_moved_from_additional_tabel_to_main_if_is_absent_in_main_but_workday_in_shift_schedule(self):
        dt = date(2021, 6, 11)
        dt_donor = date(2021, 6, 12)
        WorkerDay.objects.filter(dt=dt, is_fact=True).delete()
        WorkerDay.objects.filter(~Q(dt__in=[dt, dt_donor])).delete()
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_WORKDAY)
            self.assertEqual(main_ts_item.day_hours, 8)
            self.assertIsNone(additional_ts_item)

            donor_additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt_donor, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertIsNotNone(donor_additional_ts_item)
            self.assertEqual(donor_additional_ts_item.day_type_id, WorkerDay.TYPE_WORKDAY)
            self.assertEqual(donor_additional_ts_item.day_hours, 1)

    def test_plan_holiday_in_main_timesheet_filled_as_in_shift_schedule(self):
        dt = date(2021, 6, 11)
        WorkerDay.objects.filter(dt=dt, is_fact=True).delete()
        for wd in WorkerDay.objects.filter(dt=dt, is_fact=False):
            wd.type_id = WorkerDay.TYPE_HOLIDAY
            wd.dttm_work_start = None
            wd.dttm_work_end = None
            wd.save()
        dt_donor = date(2021, 6, 12)
        WorkerDay.objects.filter(~Q(dt__in=[dt, dt_donor])).delete()
        for employee in [self.employee_worker]:
            self._calc_timesheets(employee_id=employee.id, reraise_exc=True, dttm_now=datetime(2021, 6, 25))
            main_ts_item = TimesheetItem.objects.get(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
            additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertEqual(main_ts_item.day_type_id, WorkerDay.TYPE_WORKDAY)
            self.assertEqual(main_ts_item.day_hours, 8)
            self.assertIsNone(additional_ts_item)

            donor_additional_ts_item = TimesheetItem.objects.filter(
                employee=employee, dt=dt_donor, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).first()
            self.assertIsNotNone(donor_additional_ts_item)
            self.assertEqual(donor_additional_ts_item.day_type_id, WorkerDay.TYPE_WORKDAY)
            self.assertEqual(donor_additional_ts_item.day_hours, 1)
