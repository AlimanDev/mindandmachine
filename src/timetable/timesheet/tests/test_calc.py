from datetime import date, datetime, time

from django.db.models import Sum
from django.test import TestCase, override_settings

from src.base.models import WorkerPosition
from src.timetable.models import WorkerDay, TimesheetItem, WorkTypeName, WorkType
from src.timetable.tests.factories import WorkerDayFactory
from ._base import TestTimesheetMixin


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS=None)
class TestTimesheetCalc(TestTimesheetMixin, TestCase):
    def test_calc_timesheets(self):
        self._calc_timesheets()
        self.assertEqual(TimesheetItem.objects.count(), 30)
        self.assertEqual(TimesheetItem.objects.filter(day_type_id=WorkerDay.TYPE_WORKDAY).count(), 7)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN).count(), 0)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).count(), 0)

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
        self.assertEqual(TimesheetItem.objects.count(), 31)
        self.assertEqual(TimesheetItem.objects.filter(day_type_id='W').count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN).count(), 0)
        self.assertEqual(TimesheetItem.objects.filter(timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL).count(), 0)

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
        dt_timesheet = TimesheetItem.objects.filter(dt=dt).aggregate(total_hours_sum=Sum('day_hours') + Sum('night_hours'))
        self.assertEqual(dt_timesheet['total_hours_sum'], 11)

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
        dt_timesheet = TimesheetItem.objects.get(dt=dt)
        self.assertEqual(dt_timesheet.day_hours, 9)
        self.assertEqual(dt_timesheet.day_type, san_day)

    def test_work_type_name_and_position_mapping(self):
        """
        Получение должности по типу работ
        2 рабочих дня
        первый -- тип работ по основной должности
        второй -- тип работ по другой должности
        """
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
        self._calc_timesheets()
        dt_timesheet = TimesheetItem.objects.filter(dt=dt).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'))
        self.assertEqual(dt_timesheet['total_hours_sum'], 11)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            employee=self.employee_worker,
            position=self.employment_worker.position,
        ).count(), 2)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            employee=self.employee_worker,
            position=other_position,
        ).count(), 0)

        self.network.get_position_from_work_type_name_in_calc_timesheet = True
        self.network.save()
        self._calc_timesheets()
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            employee=self.employee_worker,
            position=self.employment_worker.position,
        ).count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            employee=self.employee_worker,
            position=other_position,
        ).count(), 1)
