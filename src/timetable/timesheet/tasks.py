import logging

from django.db.models import Max, Min

from src.base.models import Employee, Employment
from src.celery.celery import app
from .calc import TimesheetCalculator, _get_calc_periods

logger = logging.getLogger('calc_timesheets')


@app.task
def calc_timesheets(employee_id__in: list = None):
    logger.info('start calc_timesheets')
    calc_periods = _get_calc_periods()
    dt_from, dt_to = calc_periods[0][0], calc_periods[-1][1]

    if employee_id__in:
        qs = Employee.objects.filter(id__in=employee_id__in)
    else:
        qs = Employee.objects.filter(
            employments__in=Employment.objects.get_active(
                dt_from=dt_from, dt_to=dt_to,
            )
        ).distinct()

    qs = qs.annotate(
        dt_hired=Min('employments__dt_hired'),
        dt_fired=Max('employments__dt_fired'),
    )
    for employee in qs:
        TimesheetCalculator(employee=employee).calc()
    logger.info('finish calc_timesheets')
