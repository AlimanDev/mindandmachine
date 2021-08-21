from datetime import date, datetime, time

from django.test import TestCase
from django.test import override_settings

from src.timetable.models import Timesheet
from src.timetable.models import WorkerDay
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
