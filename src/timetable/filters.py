import datetime

from dateutil.relativedelta import relativedelta
from django.db.models import Subquery, OuterRef, Q
from django_filters.rest_framework import (
    FilterSet,
    BooleanFilter,
    NumberFilter,
    DateFilter,
    TimeFilter,
    CharFilter,
    OrderingFilter,
)

from src.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint


class WorkerDayFilter(FilterSet):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода")  # aa: fixme: delete
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода') # aa: fixme: delete
    is_tabel = BooleanFilter(method='filter_tabel', label="Выгрузка табеля")
    fact_tabel = BooleanFilter(method='filter_fact_tabel', label="Выгрузка табеля для Ортеки")

    def filter_tabel(self, queryset, name, value):
        if value:
            return queryset.get_tabel(network=self.request.user.network)

        return queryset

    def filter_fact_tabel(self, queryset, name, value):
        if value:
            ordered_subq = queryset.filter(
                dt=OuterRef('dt'),
                worker_id=OuterRef('worker_id'),
                is_approved=True,
            ).order_by('-is_fact', '-work_hours').values_list('id')[:1]
            return queryset.filter(
                Q(is_fact=True) | Q(~Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE), is_fact=False),
                is_approved=True,
                id=Subquery(ordered_subq),
            )

        return queryset

    class Meta:
        model = WorkerDay
        fields = {
            # 'shop_id':['exact'],
            'worker_id': ['in', 'exact'],
            'worker__username': ['in', 'exact'],
            'dt': ['gte', 'lte', 'exact', 'range'],
            'is_approved': ['exact'],
            'is_fact': ['exact'],
            'type': ['exact'],
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


class FilterSetWithInitial(FilterSet):
    """
    Класс, которые позволяет задавать дефолтные значения для фильтров через initial

    Note:
        взято отсюда:
        https://django-filter.readthedocs.io/en/master/guide/tips.html#using-initial-values-as-defaults
    """
    def __init__(self, data=None, *args, **kwargs):
        # if filterset is bound, use initial values as defaults
        if data is not None:
            # get a mutable copy of the QueryDict
            data = data.copy()

            for name, f in self.base_filters.items():
                initial = f.extra.get('initial')

                # filter param is either missing or empty, use initial as default
                if not data.get(name) and initial:
                    if callable(initial):
                        initial = initial()
                    data[name] = initial

        super().__init__(data, *args, **kwargs)


class VacancyFilter(FilterSetWithInitial):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', initial=datetime.datetime.today)
    dt_to = DateFilter(
        field_name='dt', lookup_expr='lte', initial=lambda: datetime.datetime.today() + relativedelta(months=1))
    is_vacant = BooleanFilter(field_name='worker', lookup_expr='isnull')
    shift_length_min = TimeFilter(field_name='work_hours', lookup_expr='gte')
    shift_length_max = TimeFilter(field_name='work_hours', lookup_expr='lte')
    shop_id = CharFilter(field_name='shop_id', method='filter_include_outsource')
    work_type_name = CharFilter(field_name='work_types', method='filter_by_name')
    ordering = OrderingFilter(fields=('dt', 'id', 'dttm_work_start', 'dttm_work_end'), initial='dttm_work_start')

    def filter_include_outsource(self, queryset, name, value):
        if value:
            shops = value.split(',')
            if not self.data.get('include_outsource', False):
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
            'work_types__id': ['exact', 'in'],
            'is_approved': ['exact', ],
            'is_outsource': ['exact', ],
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
