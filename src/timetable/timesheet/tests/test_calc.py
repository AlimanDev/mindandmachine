from django.test import TestCase
from django.test import override_settings

from src.timetable.models import Timesheet
from ._base import TestTimesheetMixin


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS=None)
class TestTimesheetCalc(TestTimesheetMixin, TestCase):
    def test_calc_timesheets(self):
        self._calc_timesheets()
        self.assertEqual(Timesheet.objects.count(), 30)
        self.assertEqual(Timesheet.objects.filter(fact_timesheet_type='W').count(), 7)
        self.assertEqual(Timesheet.objects.filter(main_timesheet_type='').count(), 30)
        self.assertEqual(Timesheet.objects.filter(additional_timesheet_hours__isnull=True).count(), 30)
