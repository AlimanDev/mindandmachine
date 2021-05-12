from django_filters.rest_framework import FilterSet, CharFilter

from src.timetable.models import WorkerDay


class WorkShiftFilter(FilterSet):
    worker = CharFilter(field_name='employee__tabel_code', label='Табельный номер сотрудника')
    shop = CharFilter(field_name='shop__code', label='Код подразделения')

    class Meta:
        model = WorkerDay
        fields = {
            'dt': ['exact', 'in'],
        }
