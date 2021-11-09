from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pandas as pd
from django.db.models import Sum, Q
from django.test import TestCase, override_settings
from src.base.models import SAWHSettings, SAWHSettingsMapping, Network, WorkerPosition
from src.base.tests.factories import ShopFactory
from src.timetable.models import TimesheetItem, WorkerDay
from src.timetable.models import WorkTypeName, WorkType, WorkerDayType
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
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, day_type_id=WorkerDay.TYPE_WORKDAY).count(), 0)


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
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL, dt=date(2021, 6, 7), position=other_position).count(), 1)

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
