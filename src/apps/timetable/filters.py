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

from src.apps.base.filters import BaseActiveNamedModelFilter
from src.apps.base.models import Employment
from src.apps.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint, WorkTypeName
from src.common.drf.filters import ListFilter


class WorkerDayFilter(FilterSet):
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода")  # aa: fixme: delete
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода') # aa: fixme: delete
    fact_tabel = BooleanFilter(method='filter_fact_tabel', label="Выгрузка табеля")
    fact_shop_code__in = ListFilter(
        method='filter_fact_shop_code__in',
        label='Выгрузка сотрудников подразделений '
              '+ сотрудников у которых есть хотя бы 1 фактически подтвержденный рабочий день в одном из указанных подразделений,'
              ' предполагается использование вместе с фильтром fact_tabel=true',
    )

    # параметры для совместимости с существующими интеграциями, не удалять
    worker_id = NumberFilter(field_name='employee__user_id')
    worker__username__in = ListFilter(field_name='employee__user__username', lookup_expr='in')
    employment__tabel_code__in = ListFilter(field_name='employee__tabel_code', lookup_expr='in')
    employee_id__in = ListFilter(field_name='employee_id', lookup_expr='in')

    def filter_fact_tabel(self, queryset, name, value):
        if value:
            return queryset.get_tabel()

        return queryset


    def filter_fact_shop_code__in(self, queryset, name, value):
        if value:
            fact_shop_code__in = value.split(',')
            employee_ids = list(Employment.objects.get_active(
                self.request.user.network_id,
                dt_from=self.form.cleaned_data.get('dt__gte'),
                dt_to=self.form.cleaned_data.get('dt__lte'),
            ).annotate(
                has_fact_approved_in_shop=Exists(
                    queryset.filter(
                        is_fact=True,
                        is_approved=True,
                        shop__code__in=fact_shop_code__in,
                        employee_id=OuterRef('employee_id'),
                    )
                )
            ).filter(
                Q(shop__code__in=fact_shop_code__in) |
                Q(has_fact_approved_in_shop=True),
            ).values_list('employee_id', flat=True))
            return queryset.filter(
                employee_id__in=employee_ids,
            ).distinct()

        return queryset

    class Meta:
        model = WorkerDay
        fields = {
            'shop_id':['exact'],
            'employee_id': ['exact'],
            'employee__tabel_code': ['in', 'exact'],
            'dt': ['gte', 'lte', 'exact', 'range'],
            'is_approved': ['exact'],
            'is_fact': ['exact'],
            'type': ['in', 'exact'],
            'type__is_dayoff': ['exact']
        }


class WorkerDayStatFilter(FilterSet):
    shop_id = NumberFilter(required=True)
    dt_from = DateFilter(field_name='dt', lookup_expr='gte', label="Начало периода", required=True)
    dt_to = DateFilter(field_name='dt', lookup_expr='lte', label='Окончание периода', required=True)
    employee_id = NumberFilter(field_name='employee_id')
    employee_id__in = ListFilter(field_name='employee_id', lookup_expr='in')

    class Meta:
        model = WorkerDay
        fields = (
            'shop_id',
            'dt_from',
            'dt_to',
            'employee_id',
            'employee_id__in',
        )


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
    shop_id = CharFilter(field_name='shop_id', method='filter_shops')
    outsourcing_network_id__in = CharFilter(field_name='outsources', method='filter_outsources')
    is_outsource = BooleanFilter(field_name='is_outsource')
    work_type_name = CharFilter(field_name='work_types', method='filter_by_name')
    ordering = OrderingFilter(fields=('dt', 'id', 'dttm_work_start', 'dttm_work_end'), initial='dt,dttm_work_start')
    approved_first = BooleanFilter(method='filter_approved_first')
    only_available = BooleanFilter(method='filter_only_available')

    def filter_shops(self, queryset, name, value):
        if value:
            return queryset.filter(shop_id__in=value.split(','))
        return queryset

    def filter_outsources(self, queryset, name, value):
        if value:
            return queryset.filter(outsources__id__in=value.split(',')).distinct()
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
            approved_dates = list(
                WorkerDay.objects.filter(
                    dt__gte=self.form.data['dt_from'],
                    dt__lte=self.form.data['dt_to'],
                    employee__user_id=self.request.user.id,
                    is_approved=True,
                    is_fact=False,
                ).exclude(
                    type__is_work_hours=True,
                    is_vacancy=False,
                ).values_list('dt', flat=True)
            )
            active_employment_subq = Employment.objects.filter(
                Q(dt_hired__lte=OuterRef('dt')) | Q(dt_hired__isnull=True),
                Q(dt_fired__gte=OuterRef('dt')) | Q(dt_fired__isnull=True),
                employee__user_id=self.request.user.id,
                employee__user__network_id=self.request.user.network_id,
            )
            current_network_filter = Q(shop__network_id=self.request.user.network_id, dt__in=approved_dates)
            if not self.request.user.network.allow_workers_confirm_outsource_vacancy:
                current_network_filter &= ~Q(is_outsource=True)
            return queryset.annotate(
                active_employment_exists=Exists(active_employment_subq),
                has_overlap=Exists(WorkerDay.get_overlap_qs(self.request.user.id)),
            ).filter(
                current_network_filter | 
                Q(is_outsource=True) & ~Q(shop__network_id=self.request.user.network_id), # аутсорс фильтр
                active_employment_exists=True,
                has_overlap=False,
                is_approved=True,
                employee__isnull=True,
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
            'employment_id': ['exact'],
        }


class WorkerConstraintFilter(FilterSet):
    employment_id = NumberFilter(field_name='employment_id')

    class Meta:
        model = WorkerConstraint
        fields = {
            'employment_id': ['exact'],
        }


class WorkTypeNameFilter(BaseActiveNamedModelFilter):
    shop_id = NumberFilter(field_name='work_types__shop_id')
    shop_id__in = ListFilter(field_name='work_types__shop_id', lookup_expr='in')

    class Meta:
        model = WorkTypeName
        fields = []
