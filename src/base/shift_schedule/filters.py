from django_filters.rest_framework import FilterSet

from src.base.models import (
    ShiftSchedule,
    ShiftScheduleInterval,
)


class ShiftScheduleFilter(FilterSet):
    class Meta:
        model = ShiftSchedule
        fields = {
            'year': ['exact', 'in'],
            'code': ['exact', 'in'],
        }


class ShiftScheduleIntervalFilter(FilterSet):
    class Meta:
        model = ShiftScheduleInterval
        fields = {
            'code': ['exact', 'in'],
            'shift_schedule_id': ['exact', 'in'],
            'shift_schedule__code': ['exact', 'in'],
            'employee_id': ['exact', 'in'],
            'employee__code': ['exact', 'in'],
            'dt_start': ['exact', 'lte', 'gte'],
            'dt_end': ['exact', 'lte', 'gte'],
        }
