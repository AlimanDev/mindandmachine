from django_filters.rest_framework import FilterSet
from src.util.drf.filters import ListFilter

from src.timetable.models import AttendanceRecords


class AttendanceRecordsFilter(FilterSet):
    employee_id__in = ListFilter(method='filter_employee_id__in')

    def filter_employee_id__in(self, queryset, name, value):
        if value:
            value = value.split(',')
            return queryset.filter(employee_id__in=value)
        return queryset

    class Meta:
        model = AttendanceRecords
        fields = {
            'type': ['exact'],
            'dt': ['exact', 'gte', 'lte'],
            'shop_id': ['exact', 'in'],
            'user_id': ['exact', 'in'],
            'employee_id': ['exact'],
        }
