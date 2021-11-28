from django.db.models import Sum, Q, F

from src.base.models import (
    ShiftScheduleInterval,
)


def get_shift_schedule(
        network_id, dt__gte, dt__lte, employee_id=None, employee_id__in=None, employment__in=None,
        group_by1_lookup='employee_id', group_by2_lookup='shift_schedule__days__dt'):
    assert employee_id or employee_id__in or employment__in

    filter_kwargs = {}
    if network_id:
        filter_kwargs['employee__user__network_id'] = network_id
        filter_kwargs['shift_schedule__network_id'] = network_id
    if employee_id:
        filter_kwargs['employee_id'] = employee_id
    if employee_id__in:
        filter_kwargs['employee_id__in'] = employee_id__in
    if employment__in:
        filter_kwargs['employee__employments__dt_fired__gte'] = dt__lte
        filter_kwargs['employee__employments__dt_hired__lte'] = dt__gte
        filter_kwargs['shift_schedule__days__dt__gte'] = F('employee__employments__dt_hired')
        filter_kwargs['shift_schedule__days__dt__lte'] = F('employee__employments__dt_fired')
        if employment__in:
            filter_kwargs['employee__employments__in'] = employment__in

    values_list = [
        group_by1_lookup,
        group_by2_lookup,
        'shift_schedule__days__day_type_id',
        'shift_schedule__days__work_hours',
    ]
    qs = ShiftScheduleInterval.objects.filter(
        Q(shift_schedule__days__dt__gte=dt__gte) & Q(
            shift_schedule__days__dt__gte=F('dt_start')),
        Q(shift_schedule__days__dt__lte=dt__lte) & Q(
            shift_schedule__days__dt__lte=F('dt_end')),
        **filter_kwargs,
    ).values(
        *values_list,
    )
    data = {}
    for i in qs:
        data.setdefault(str(i[group_by1_lookup]), {}).setdefault(str(i[group_by2_lookup]), {
            'day_type': i['shift_schedule__days__day_type_id'],
            'work_hours': i['shift_schedule__days__work_hours'],
        })
    return data
