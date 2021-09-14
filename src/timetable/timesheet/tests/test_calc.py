from datetime import date, datetime, time

from django.test import TestCase
from django.test import override_settings

from src.timetable.models import WorkerDay, Timesheet
from src.timetable.tests.factories import WorkerDayFactory
from ._base import TestTimesheetMixin


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS=None)
class TestTimesheetCalc(TestTimesheetMixin, TestCase):
    def test_calc_timesheets(self):
        self._calc_timesheets()
        self.assertEqual(Timesheet.objects.count(), 30)
        self.assertEqual(Timesheet.objects.filter(fact_timesheet_type_id='W').count(), 7)
        self.assertEqual(Timesheet.objects.filter(main_timesheet_type__isnull=True).count(), 30)
        self.assertEqual(Timesheet.objects.filter(additional_timesheet_hours__isnull=True).count(), 30)

    def test_calc_timesheet_for_specific_period(self):
        dttm_now = datetime(2021, 8, 7)
        dt_wd = date(2021, 5, 3)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt_wd,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt_wd, time(10)),
            dttm_work_end=datetime.combine(dt_wd, time(20)),
        )
        self._calc_timesheets(dttm_now=dttm_now, dt_from=date(2021, 5, 1), dt_to=date(2021, 5, 31))
        self.assertEqual(Timesheet.objects.count(), 31)
        self.assertEqual(Timesheet.objects.filter(fact_timesheet_type_id='W').count(), 1)
        self.assertEqual(Timesheet.objects.filter(main_timesheet_type__isnull=True).count(), 31)
        self.assertEqual(Timesheet.objects.filter(additional_timesheet_hours__isnull=True).count(), 31)

    def test_calc_timesheets_with_multiple_workerdays_on_one_date(self):
        dt = date(2021, 6, 7)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(dt, time(4)),
            dttm_work_end=datetime.combine(dt, time(7)),
        )
        self._calc_timesheets()
        dt_timesheet = Timesheet.objects.get(dt=dt)
        self.assertEqual(dt_timesheet.fact_timesheet_total_hours, 11)

    def test_calc_fact_timesheet_for_wd_type_with_is_work_hours_false(self):
        san_day = self._create_san_day()
        dt = date(2021, 6, 7)
        WorkerDay.objects.filter(dt=dt, is_fact=True, is_approved=True).delete()
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type=san_day,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(20)),
        )
        self._calc_timesheets()
        dt_timesheet = Timesheet.objects.get(dt=dt)
        self.assertEqual(dt_timesheet.fact_timesheet_total_hours, 9)
        self.assertEqual(dt_timesheet.fact_timesheet_type, san_day)
