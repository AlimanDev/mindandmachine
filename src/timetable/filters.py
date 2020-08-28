from django_filters.rest_framework import FilterSet, BooleanFilter, NumberFilter, DateFilter, TimeFilter, CharFilter
from src.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint
from django.db.models import Q

class WorkerDayFilter(FilterSet):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода")
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода')
    is_approved = BooleanFilter(field_name='worker_day_approve_id', method='filter_approved')

    def filter_approved(self, queryset, name, value):
        if value:
            return queryset.filter(worker_day__approve_id__isnull=False)
        else:
            # неподтвержденная версия, это на самом деле последняя версия, а последняя эта та, у которой нет детей
            return queryset.filter(
                is_fact=False,
                child__id__isnull=True
            )

    class Meta:
        model = WorkerDay
        fields = {
            # 'shop_id':['exact'],
            'worker_id':['in','exact'],
            'worker__username': ['in', 'exact'],
            'dt': ['gte', 'lte', 'exact', 'range'],
            'is_approved': ['exact'],
            'is_fact': ['exact']
        }


class WorkerDayStatFilter(FilterSet):
    shop_id = NumberFilter(required=True)
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода", required=True)
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода', required=True)

    class Meta:
        model = WorkerDay
        fields = {
            'worker_id': ['exact', 'in'],
        }


class VacancyFilter(FilterSet):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte')
    dt_to = DateFilter(field_name='dt', lookup_expr='lte')
    is_vacant = BooleanFilter(field_name='worker', lookup_expr='isnull')
    shift_length_min = TimeFilter(field_name='work_hours', lookup_expr='gte')
    shift_length_max = TimeFilter(field_name='work_hours', lookup_expr='lte')
    shop = CharFilter(field_name='shop_id', method='filter_include_outsource')
    work_type_name = CharFilter(field_name='work_types', method='filter_by_name')

    def filter_include_outsource(self, queryset, name, value):
        if value:
            shops = value.split(',')
            if not self.request.query_params.get('include_outsource', False):
                return queryset.filter(shop_id__in=shops)
            return queryset.filter(
                Q(shop_id__in=shops) | Q(is_outsource=True),
            )
        return queryset

    def filter_by_name(self, queryset, name, value):
        names = value.split(',')
        return queryset.filter(
            work_types__work_type_name_id__in=names,
        )

    class Meta:
        model = WorkerDay
        fields = {
            'work_types__id':['exact', 'in'],
            'is_approved': ['exact',],
            'is_outsource': ['exact',],
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

