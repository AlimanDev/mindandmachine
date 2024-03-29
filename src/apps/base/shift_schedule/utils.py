from django.db.models import Sum, Q, F

from src.apps.base.models import (
    ShiftScheduleInterval,
    ShiftSchedule,
)


def get_shift_schedule(
        network_id, dt__gte, dt__lte, employee_id=None, employee_id__in=None, employment__in=None):
    assert employee_id or employee_id__in or employment__in

    q = Q()
    if network_id:
        q &= Q(
            employee__user__network_id=network_id,
            shift_schedule__network_id=network_id,
        )
    if employee_id:
        q &= Q(
            employee_id=employee_id,
        )
    if employee_id__in:
        q &= Q(
            employee_id__in=employee_id__in,
        )
    if employment__in:
        q &= Q(
            Q(employee__employments__dt_fired__gte=dt__gte) | Q(employee__employments__dt_fired__isnull=True),
            Q(employee__employments__dt_hired__lte=dt__lte) | Q(employee__employments__dt_hired__isnull=True),
            Q(shift_schedule__days__dt__gte=F('employee__employments__dt_hired')) | Q(
                employee__employments__dt_hired__isnull=True),
            Q(shift_schedule__days__dt__lte=F('employee__employments__dt_fired')) | Q(
                employee__employments__dt_fired__isnull=True),
            employee__employments__in=employment__in,
        )

    values_list = [
        'group_by1_lookup',
        'group_by2_lookup',
    ]
    if not employment__in:
        values_list.append('day_type_id')

    qs = ShiftScheduleInterval.objects.filter(
        Q(shift_schedule__days__dt__gte=dt__gte) & Q(
            shift_schedule__days__dt__gte=F('dt_start')),
        Q(shift_schedule__days__dt__lte=dt__lte) & Q(
            shift_schedule__days__dt__lte=F('dt_end')),
        q,
    ).annotate(
        group_by1_lookup=F('employee__employments__id' if employment__in else 'employee_id'),
        group_by2_lookup=F('shift_schedule__days__dt'),
        day_type_id=F('shift_schedule__days__day_type_id'),
    ).values(
        *values_list,
    ).annotate(
        work_hours_sum=Sum('shift_schedule__days__work_hours'),
        day_hours_sum=Sum('shift_schedule__days__day_hours'),
        night_hours_sum=Sum('shift_schedule__days__night_hours'),
    )

    data = {}
    for i in qs:
        if employment__in:
            data.setdefault(str(i['group_by1_lookup']), {}).setdefault(str(i['group_by2_lookup']), {
                'work_hours': i['work_hours_sum'],
                'day_hours': i['day_hours_sum'],
                'night_hours': i['night_hours_sum'],
            })
        else:
            data.setdefault(str(i['group_by1_lookup']), {}).setdefault(str(i['group_by2_lookup']), {
                'day_type': i['day_type_id'],
                'work_hours': i['work_hours_sum'],
                'day_hours': i['day_hours_sum'],
                'night_hours': i['night_hours_sum'],
            })
    return data
