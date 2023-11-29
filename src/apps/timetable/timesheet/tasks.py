import logging
from datetime import date

from celery_singleton import Singleton
from django.db import transaction

from src.apps.base.models import Employee, Employment
from src.adapters.celery.celery import app
from src.apps.timetable.models import WorkerDayType, WorkTypeName
from src.common.models_converter import Converter
from src.apps.timetable.timesheet.services.calc import TimesheetCalculatorService, _get_calc_periods
from .utils import delete_hanging_timesheet_items
from ..worker_day.stat import get_month_range

logger = logging.getLogger('calc_timesheets')


@app.task(base=Singleton)
def calc_timesheets(employee_id__in: list = None, dt_from=None, dt_to=None, reraise_exc=False, cleanup=True):
    assert (dt_from and dt_to) or (dt_from is None and dt_to is None)
    if dt_from and dt_to:
        if isinstance(dt_from, str):
            dt_from = Converter.parse_date(dt_from)
        if isinstance(dt_to, str):
            dt_to = Converter.parse_date(dt_to)
        assert dt_from.month == dt_to.month
    logger.info('start calc_timesheets')

    calc_periods = _get_calc_periods(dt_from=dt_from, dt_to=dt_to)
    if employee_id__in:
        qs = Employee.objects.filter(id__in=employee_id__in).select_related('user__network')
    else:
        qs = Employee.objects.filter(
            employments__in=Employment.objects.get_active(
                dt_from=calc_periods[0][0], dt_to=calc_periods[-1][1],
            )
        ).select_related('user__network').distinct()

    # TODO: переделать
    # qs = qs.annotate(
    #     dt_hired=Min('employments__dt_hired'),
    #     dt_fired=Max('employments__dt_fired'),
    # )
    wd_types_dict = WorkerDayType.get_wd_types_dict()
    work_type_names_dict = WorkTypeName.get_work_type_names_dict()
    for employee in qs:
        try:
            TimesheetCalculatorService(
                employee=employee, dt_from=dt_from, dt_to=dt_to, wd_types_dict=wd_types_dict,
                work_type_names_dict=work_type_names_dict, calc_periods=calc_periods).calc()
        except Exception as e:
            logger.exception(e)
            if reraise_exc:
                raise e
    
    if cleanup:
        res = delete_hanging_timesheet_items(calc_periods)
        if res[0]:
            logger.info(f'deleted {res[0]} hanging TimesheetItems')
    
    logger.info('finish calc_timesheets')


def recalc_timesheet_on_data_change(groupped_data: dict[int, tuple[date]]):
    # recalculate timesheet for period when employees' workdays changed
    for employee_id, dates in groupped_data.items():
        periods = set()
        for dt in dates:
            dt_start, dt_end = get_month_range(year=dt.year, month_num=dt.month)
            periods.add((dt_start, dt_end))
        for period_start, period_end in periods:
            transaction.on_commit(
                lambda _employee_id=employee_id, _period_start=Converter.convert_date(period_start),
                        _period_end=Converter.convert_date(period_end): calc_timesheets.apply_async(
                    kwargs=dict(
                        employee_id__in=[_employee_id],
                        dt_from=_period_start,
                        dt_to=_period_end,
                    ))
                )
