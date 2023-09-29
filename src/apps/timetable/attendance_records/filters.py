from django_filters.rest_framework import FilterSet
from src.common.drf.filters import ListFilter

from src.apps.timetable.models import AttendanceRecords


class AttendanceRecordsFilter(FilterSet):
    employee_id__in = ListFilter(field_name='employee_id', lookup_expr='in')

    class Meta:
        model = AttendanceRecords
        fields = {
            'type': ['exact'],
            'dt': ['exact', 'gte', 'lte'],
            'shop_id': ['exact', 'in'],
            'user_id': ['exact', 'in'],
            'employee_id': ['exact'],
        }
