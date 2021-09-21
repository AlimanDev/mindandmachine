import logging

from django.db.models import Max, Min

from src.base.models import Employee, Employment
from src.celery.celery import app
from src.timetable.models import WorkerDayType
from src.util.models_converter import Converter
from .calc import TimesheetCalculator, _get_calc_periods

logger = logging.getLogger('calc_timesheets')


@app.task
def calc_timesheets(employee_id__in: list = None, dt_from=None, dt_to=None):
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
        qs = Employee.objects.filter(id__in=employee_id__in)
    else:
        qs = Employee.objects.filter(
            employments__in=Employment.objects.get_active(
                dt_from=calc_periods[0][0], dt_to=calc_periods[-1][1],
            )
        ).distinct()

    qs = qs.annotate(
        dt_hired=Min('employments__dt_hired'),
        dt_fired=Max('employments__dt_fired'),
    )
    wd_types_dict = WorkerDayType.get_wd_types_dict()
    for employee in qs:
        try:
            TimesheetCalculator(employee=employee, dt_from=dt_from, dt_to=dt_to, wd_types_dict=wd_types_dict).calc()
        except Exception as e:
            logger.exception(e)
    logger.info('finish calc_timesheets')
