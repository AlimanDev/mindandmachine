from django_filters.rest_framework import FilterSet

from src.timetable.models import AttendanceRecords


class AttendanceRecordsFilter(FilterSet):
    class Meta:
        model = AttendanceRecords
        fields = {
            'type': ['exact'],
            'dt': ['exact', 'gte', 'lte'],
            'shop_id': ['exact', 'in'],
            'user_id': ['exact', 'in'],
            'employee_id': ['exact', 'in'],
        }
