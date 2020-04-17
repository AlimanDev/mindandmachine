from django_filters.rest_framework import FilterSet, BooleanFilter, NumberFilter, DateFilter
from src.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint
from django.db.models import Q

class WorkerDayFilter(FilterSet):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода")
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода')
    is_approved = BooleanFilter(field_name='worker_day_approve_id', method='filter_approved')

    def filter_approved(self, queryset, name, value):
        if value:
            return queryset.filter(worker_day_approve_id__isnull=False)
        else:
            # Подтвержденная версия, это на самом деле последняя версия
            return queryset.filter(
                is_fact=False,
                child__id__isnull=True
            )

    class Meta:
        model = WorkerDay
        fields = {
            # 'shop_id':['exact'],
            'worker_id':['in','exact'],
            'dt': ['gte', 'lte', 'exact', 'range'],
            'is_approved': ['exact'],
            'is_fact': ['exact']
        }


class WorkerDayMonthStatFilter(FilterSet):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода", required=True)
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода', required=True)

    #shop_id определен в
    # shop_id = NumberFilter(required=True)

    class Meta:
        model = WorkerDay
        fields = {
            # 'shop_id': ['exact'],
            'worker_id': ['exact', 'in'],
        }

class EmploymentWorkTypeFilter(FilterSet):
    shop_id=NumberFilter(field_name='work_type__shop_id')
    class Meta:
        model = EmploymentWorkType
        fields = {
            'shop_id': ['exact'],
            'employment_id': ['exact'],
        }


class WorkerConstraintFilter(FilterSet):
    employment_id = NumberFilter(field_name='employment_id')
    class Meta:
        model = WorkerConstraint
        fields = {
            'employment_id': ['exact'],
        }

