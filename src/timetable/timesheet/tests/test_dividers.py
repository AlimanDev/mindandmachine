from datetime import datetime, time, date
from decimal import Decimal

import pandas as pd
from django.db.models import Sum, Q
from django.test import TestCase, override_settings

from src.timetable.models import Timesheet
from src.timetable.models import WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from ._base import TestTimesheetMixin


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS='nahodka')
class TestNahodkaDivider(TestTimesheetMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

    def test_48h_week_rest(self):
        self._calc_timesheets()
        self.assertEqual(Timesheet.objects.count(), 30)
        self.assertEqual(Timesheet.objects.filter(fact_timesheet_type_id='W').count(), 7)
        self.assertEqual(Timesheet.objects.filter(main_timesheet_type_id='W').count(), 5)
        self.assertEqual(Timesheet.objects.filter(additional_timesheet_hours__gt=0).count(), 2)

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
        self.assertEqual(Timesheet.objects.filter(
            dt=dt, employee=self.employee_worker).get().fact_timesheet_total_hours, Decimal('14.00'))
        self.assertEqual(Timesheet.objects.filter(
            dt=dt, employee=self.employee_worker).get().main_timesheet_total_hours, Decimal('12.00'))
        self.assertEqual(Timesheet.objects.filter(
            dt=dt, employee=self.employee_worker).get().additional_timesheet_hours, Decimal('2.00'))

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
        timesheet_hours = Timesheet.objects.aggregate(
            fact_hours_sum=Sum('fact_timesheet_total_hours'),
            main_hours_sum=Sum('main_timesheet_total_hours'),
            additional_hours_sum=Sum('additional_timesheet_hours'),
        )
        self.assertEqual(timesheet_hours['fact_hours_sum'], 190)
        self.assertEqual(timesheet_hours['main_hours_sum'], 167)  # норма на июнь 2021
        self.assertEqual(timesheet_hours['additional_hours_sum'], 23)

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
        timesheet_hours = Timesheet.objects.aggregate(
            fact_hours_sum=Sum('fact_timesheet_total_hours'),
            main_hours_sum=Sum('main_timesheet_total_hours'),
            additional_hours_sum=Sum('additional_timesheet_hours'),
        )
        self.assertEqual(timesheet_hours['fact_hours_sum'], 210)
        self.assertEqual(timesheet_hours['main_hours_sum'], 150)
        self.assertEqual(timesheet_hours['additional_hours_sum'], 60)

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
        timesheet_hours = Timesheet.objects.aggregate(
            fact_hours_sum=Sum('fact_timesheet_total_hours'),
            main_hours_sum=Sum('main_timesheet_total_hours'),
            additional_hours_sum=Sum('additional_timesheet_hours'),
        )
        self.assertEqual(timesheet_hours['fact_hours_sum'], 169)
        self.assertEqual(timesheet_hours['main_hours_sum'], 156)
        self.assertEqual(timesheet_hours['additional_hours_sum'], 13)

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
        timesheet_hours = Timesheet.objects.aggregate(
            fact_all_hours_sum=Sum('fact_timesheet_total_hours'),
            fact_work_hours_sum=Sum('fact_timesheet_total_hours', filter=Q(fact_timesheet_type__is_work_hours=True)),
            main_hours_sum=Sum('main_timesheet_total_hours'),
            additional_hours_sum=Sum('additional_timesheet_hours'),
        )
        self.assertEqual(timesheet_hours['fact_all_hours_sum'], 169)
        self.assertEqual(timesheet_hours['fact_work_hours_sum'], 117)
        self.assertEqual(timesheet_hours['main_hours_sum'], 108)
        self.assertEqual(timesheet_hours['additional_hours_sum'], 9)  # ушло в доп. по кол-ву часов в сутках > 12

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
        timesheet = Timesheet.objects.get(employee=self.employee_worker, dt=date(2021, 6, 1))
        self.assertEqual(timesheet.main_timesheet_type_id, WorkerDay.TYPE_VACATION)

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
        self.assertEqual(Timesheet.objects.filter(fact_timesheet_type_id=WorkerDay.TYPE_WORKDAY).count(), 0)
