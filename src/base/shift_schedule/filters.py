from django_filters.rest_framework import FilterSet

from src.base.models import ShiftSchedule


class ShiftScheduleFilter(FilterSet):
    class Meta:
        model = ShiftSchedule
        fields = {
            'year': ['exact', 'in'],
            'code': ['exact', 'in'],
        }
