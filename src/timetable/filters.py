import datetime

from dateutil.relativedelta import relativedelta
from django.db.models import Subquery, OuterRef, Q, Exists
from django_filters.rest_framework import (
    FilterSet,
    BooleanFilter,
    NumberFilter,
    DateFilter,
    TimeFilter,
    CharFilter,
    OrderingFilter,
)

from src.base.models import Employment
from src.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint
from src.base.models import Employment


class WorkerDayFilter(FilterSet):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода")  # aa: fixme: delete
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода') # aa: fixme: delete
    fact_tabel = BooleanFilter(method='filter_fact_tabel', label="Выгрузка табеля")

    # параметры для совместимости с существующими интеграциями, не удалять
    worker_id = NumberFilter(field_name='employee__user_id')
    worker__username__in = CharFilter(field_name='employee__user__username', method='field_in')
    employment__tabel_code__in = CharFilter(field_name='employee__tabel_code', method='field_in')

    def filter_fact_tabel(self, queryset, name, value):
        if value:
            return queryset.get_tabel()

        return queryset

    def field_in(self, queryset, name, value):
        filt = {
            f'{name}__in': value.split(',')
        }
        return queryset.filter(**filt)

    class Meta:
        model = WorkerDay
        fields = {
            # 'shop_id':['exact'],
            'employee_id': ['in', 'exact'],
            'employee__tabel_code': ['in', 'exact'],
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
            'employee_id': ['exact', 'in'],
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
    is_vacant = BooleanFilter(field_name='employee', lookup_expr='isnull')
    shift_length_min = TimeFilter(field_name='work_hours', lookup_expr='gte')
    shift_length_max = TimeFilter(field_name='work_hours', lookup_expr='lte')
    shop_id = CharFilter(field_name='shop_id', method='filter_include_outsource')
    work_type_name = CharFilter(field_name='work_types', method='filter_by_name')
    ordering = OrderingFilter(fields=('dt', 'id', 'dttm_work_start', 'dttm_work_end'), initial='dttm_work_start')
    approved_first = BooleanFilter(method='filter_approved_first')
    only_available = BooleanFilter(method='filter_only_available')

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

    def filter_approved_first(self, queryset, name, value):
        if value:
            return queryset.filter(
                id=Subquery(
                    WorkerDay.objects.filter(
                        Q(Q(employee__isnull=True) & Q(id=OuterRef('id'))) | Q(employee_id=OuterRef('employee_id')),
                        dt=OuterRef('dt'),
                        is_fact=OuterRef('is_fact'),
                        is_vacancy=OuterRef('is_vacancy'),
                        dttm_work_start=OuterRef('dttm_work_start'),
                        dttm_work_end=OuterRef('dttm_work_end'),
                    ).order_by('-is_approved').values_list('id')[:1]
                ),
            )

        return queryset

    def filter_only_available(self, queryset, name, value):
        if value:
            approved_subq = WorkerDay.objects.filter(
                dt=OuterRef('dt'),
                employee__user_id=self.request.user.id,
                is_approved=True,
                is_fact=False,
            )
            active_employment_subq = Employment.objects.filter(
                Q(dt_hired__lte=OuterRef('dt')) | Q(dt_hired__isnull=True),
                Q(dt_fired__gte=OuterRef('dt')) | Q(dt_fired__isnull=True),
                employee__user_id=self.request.user.id,
                employee__user__network_id=self.request.user.network_id,
            )
            worker_day_paid_subq = WorkerDay.objects.filter(
                dt=OuterRef('dt'),
                employee__user_id=self.request.user.id,
                is_approved=True,
                is_fact=False,
                type__in=WorkerDay.TYPES_PAID,
            )
            return queryset.annotate(
                approved_exists=Exists(approved_subq),
                active_employment_exists=Exists(active_employment_subq),
                worker_day_type_paid=Exists(worker_day_paid_subq),
            ).filter(
                # Q(shop__network_id=self.request.user.network_id) | Q(is_outsource=True), # аутсорс фильтр
                approved_exists=True,
                active_employment_exists=True,
                worker_day_type_paid=False,
            )
        return queryset

    class Meta:
        model = WorkerDay
        fields = {
            'work_types__id': ['exact', 'in'],
            'is_fact': ['exact', ],
            'is_approved': ['exact', ],
            'is_outsource': ['exact', ],
        }


class EmploymentWorkTypeFilter(FilterSet):
    shop_id = NumberFilter(field_name='work_type__shop_id')

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
