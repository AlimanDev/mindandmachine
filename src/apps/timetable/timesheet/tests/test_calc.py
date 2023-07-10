from datetime import date, datetime, time, timedelta

from django.db.models import Sum
from django.test import TestCase, override_settings

from src.apps.base.models import Employment, WorkerPosition
from src.apps.base.tests import (
    ShopFactory,
    UserFactory,
    GroupFactory,
    EmploymentFactory,
    NetworkFactory,
    EmployeeFactory,
    WorkerPositionFactory,
    BreakFactory,
)
from src.apps.timetable.models import WorkerDay, TimesheetItem, WorkTypeName, WorkType, WorkerDayType
from src.apps.timetable.tests.factories import WorkerDayFactory
from ._base import TestTimesheetMixin


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

    def test_vacation_added_to_fact_table_if_there_are_allowed_additional_type_in_fact(self):
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
        dt = date(2021, 6, 7)
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
            work_hours=timedelta(hours=10),
        )
        self._calc_timesheets()
        dt_timesheet = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(dt_timesheet['total_hours_sum'], 19)

        # проверка пересчета для дней в прошлом
        self._calc_timesheets(
            dt_from=date(2021, 6, 1),
            dt_to=date(2021, 6, 30),
            dttm_now=datetime(2021, 10, 1),
        )
        dt_timesheet = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(dt_timesheet['total_hours_sum'], 19)

    def test_both_vacation_and_allowed_additional_type_added_from_plan(self):
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
        dt = date(2021, 6, 7)
        WorkerDay.objects.filter(dt=dt, is_fact=True, is_approved=True).delete()
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
            work_hours=timedelta(hours=10),
        )
        self._calc_timesheets()
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).count(), 2)
        dt_timesheet = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(dt_timesheet['total_hours_sum'], 19)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            day_type_id=WorkerDay.TYPE_VACATION,
            day_hours=10,
        ).count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            day_type_id=WorkerDay.TYPE_WORKDAY,
            day_hours=9,
        ).count(), 1)

        # проверка пересчета для дней в прошлом
        self._calc_timesheets(
            dt_from=date(2021, 6, 1),
            dt_to=date(2021, 6, 30),
            dttm_now=datetime(2021, 10, 1),
        )
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).count(), 2)
        dt_timesheet = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(dt_timesheet['total_hours_sum'], 10)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            day_type_id=WorkerDay.TYPE_VACATION,
            day_hours=10,
        ).count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            day_type_id=WorkerDay.TYPE_ABSENSE,
            day_hours=0,
        ).count(), 1)

        absence = self.wd_types_dict.get(WorkerDay.TYPE_ABSENSE)
        absence.is_work_hours = True
        absence.save()
        self._calc_timesheets(
            dt_from=date(2021, 6, 1),
            dt_to=date(2021, 6, 30),
            dttm_now=datetime(2021, 10, 1),
        )
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).count(), 2)
        dt_timesheet = TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
        ).aggregate(
            total_hours_sum=Sum('day_hours') + Sum('night_hours'),
        )
        self.assertEqual(dt_timesheet['total_hours_sum'], 19)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            day_type_id=WorkerDay.TYPE_VACATION,
            day_hours=10,
        ).count(), 1)
        self.assertEqual(TimesheetItem.objects.filter(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            dt=dt,
            day_type_id=WorkerDay.TYPE_ABSENSE,
            day_hours=9,
        ).count(), 1)

    def test_calc_fact_without_plan_with_holiday_allowed_additional_types(self):
        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        holiday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_HOLIDAY,
        ).get()
        holiday_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL
        holiday_type.is_work_hours = True
        holiday_type.is_dayoff = True
        holiday_type.save()
        holiday_type.allowed_additional_types.add(workday_type)
        dt = date(2021, 6, 7)
        WorkerDay.objects.filter(dt=dt, is_fact=False).delete()
        self._calc_timesheets()

    def test_calc_for_only_days_in_past(self):
        WorkerDay.objects.filter(is_fact=True).delete()
        dttm_now = datetime(2021, 6, 10, 10)
        self.user_worker.network.set_settings_value('timesheet_only_day_in_past', True)
        self.user_worker.network.save()
        self._calc_timesheets(dttm_now=dttm_now, dt_from=date(2021, 6, 1), dt_to=date(2021, 6, 30))
        self.assertEqual(TimesheetItem.objects.filter(
            employee=self.employee_worker, timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT).count(), 9)

    def test_get_dayoff_from_plan_if_fact_workday_has_zero_work_hours(self):
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()
        dt = date(2021, 6, 7)
        WorkerDay.objects.filter(dt=dt, is_fact=False, is_approved=True).delete()
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=WorkerDay.TYPE_VACATION,
        )
        fact_wd = WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=dt).first()
        fact_wd.save()
        self._calc_timesheets()
        dt_timesheet = TimesheetItem.objects.get(dt=dt)
        self.assertEqual(dt_timesheet.day_type_id, WorkerDay.TYPE_VACATION)

    def test_delete_hanging_timesheet_items(self):
        dt = date.today()
        self._calc_timesheets(dttm_now=dt, cleanup=False)
        count_before = TimesheetItem.objects.count()
        self._calc_timesheets(dttm_now=dt) # cleanup=True
        self.assertEqual(count_before, TimesheetItem.objects.count())
        empl = EmploymentFactory(
            dt_hired=(dt - timedelta(101)),
            dt_fired=(dt - timedelta(100))
        )
        TimesheetItem.objects.create(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            employee=empl.employee,
            dt=dt,
            day_type_id=WorkerDay.TYPE_WORKDAY,
        )
        self._calc_timesheets(dttm_now=dt)
        self.assertEqual(count_before, TimesheetItem.objects.count())
