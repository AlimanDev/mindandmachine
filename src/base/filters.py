from django.db.models import Q
from django_filters.rest_framework import FilterSet, DateFilter, NumberFilter, CharFilter, BooleanFilter, OrderingFilter

from src.base.models import Employment, User, Notification, Subscribe, Shop, ShopSchedule, Employee
from src.util.drf.filters import ListFilter, QCharFilter, QNumberFilter, QListFilter, QDateFilter
from src.util.drf.filterset import QFilterSet


class BaseActiveNamedModelFilter(FilterSet):
    name = CharFilter(field_name='name', lookup_expr='icontains')
    name__in = ListFilter(field_name='name', lookup_expr='in')
    code = CharFilter(field_name='code', lookup_expr='exact')
    code__in = ListFilter(field_name='code', lookup_expr='in')
    id__in = ListFilter(field_name='id', lookup_expr='in')


class EmploymentFilter(FilterSet):
    dt_from = DateFilter(method='gte_or_null')
    dt_to = DateFilter(field_name='dt_hired', lookup_expr='lte', label='Окончание периода')
    shop_code = CharFilter(field_name='shop__code', label='Код магазина')
    user_id = CharFilter(field_name='employee__user_id', label='ID пользователя')
    user_id__in = ListFilter(field_name='employee__user_id', label='ID пользователя', lookup_expr='in')
    username = CharFilter(field_name='employee__user__username', label='Логин пользователя')
    username__in = ListFilter(field_name='employee__user__username', label='Логин пользователя', lookup_expr='in')
    mine = BooleanFilter(method='filter_mine', label='Сотрудники моих магазинов')
    order_by = OrderingFilter(fields=('user__last_name', 'user__first_name', 'position__ordering', 'position__name'))

    def gte_or_null(self, queryset, name, value):
        return queryset.filter(
            Q(dt_fired__gte=value) | Q(dt_fired__isnull=True)
        )

    def filter_mine(self, queryset, name, value):
        if value:
            return queryset.filter(
                shop__in=Shop.objects.get_queryset_descendants(
                    queryset=Shop.objects.filter(
                        id__in=Employment.objects.get_active(
                            network_id=self.request.user.network_id,
                            employee__user=self.request.user,
                        ).values_list('shop_id', flat=True),
                    ),
                    include_self=True,
                )
            )
        return queryset

    class Meta:
        model = Employment
        fields = {
            'id': ['in'],
            'shop_id': ['exact', 'in'],
            'employee_id': ['exact', 'in'],
            'employee__tabel_code': ['exact', 'in'],
            'is_visible': ['exact',]
        }


class UserFilter(FilterSet):
    shop_id = NumberFilter(field_name='employees__employments__shop_id')
    shop_id__in = ListFilter(field_name='employees__employments__shop_id', lookup_expr='in')
    shop_code = CharFilter(field_name='employees__employments__shop__code', label='Код магазина')
    shop_code__in = ListFilter(field_name='employees__employments__shop__code', lookup_expr='in')
    last_name = CharFilter(field_name='last_name', lookup_expr='icontains')
    first_name = CharFilter(field_name='first_name', lookup_expr='icontains')
    position_id__in = ListFilter(field_name='employees__employments__position_id', lookup_expr='in')
    work_type_id__in = ListFilter(field_name='employees__employments__work_types__work_type__work_type_name_id', lookup_expr='in')
    worker_day_type__in = ListFilter(field_name='employees__worker_days__type', lookup_expr='in')
    worker_day_dt__in = ListFilter(field_name='employees__worker_days__dt', lookup_expr='in')

    employments__dt_from = DateFilter(method='employments_dt_from')
    employments__dt_to = DateFilter(method='employments_dt_to')

    tabel_code = CharFilter(field_name='employees__tabel_code')
    tabel_code__in = ListFilter(field_name='employees__tabel_code', lookup_expr='in')

    def employments_dt_from(self, queryset, name, value):
        return queryset.filter(
            Q(employees__employments__dt_fired__gte=value) | Q(employees__employments__dt_fired__isnull=True),
        )

    def employments_dt_to(self, queryset, name, value):
        return queryset.filter(
            Q(employees__employments__dt_hired__lte=value) | Q(employees__employments__dt_hired__isnull=True),
        )

    def shop_id_in(self, queryset, name, value):
        return queryset.filter(
            employees__employments__shop_id__in=value.split(','),
        )

    class Meta:
        model = User
        fields = {
            'id': ['exact', 'in'],
            'username': ['exact', 'in'],
            'last_name': ['in', ],
            'shop_id': ['exact', 'in'],
            'shop_code': ['exact'],
        }


class EmployeeFilter(QFilterSet):
    shop_id = QNumberFilter(field_name='employments__shop_id')
    shop_id__in = QListFilter(field_name='employments__shop_id', lookup_expr='in')
    shop_code = QCharFilter(field_name='employments__shop__code', label='Код магазина')
    shop_code__in = QListFilter(field_name='employments__shop__code', lookup_expr='in')
    last_name = QCharFilter(field_name='user__last_name', lookup_expr='icontains')
    first_name = QCharFilter(field_name='user__first_name', lookup_expr='icontains')
    username = QCharFilter(field_name='user__username', lookup_expr='icontains')
    position_id__in = QListFilter(field_name='employments__position_id', lookup_expr='in')
    work_type_id__in = QListFilter(field_name='employments__work_types__work_type__work_type_name_id',
                                  lookup_expr='in')
    worker_day_type__in = QListFilter(field_name='worker_days__type', lookup_expr='in')
    worker_day_dt__in = QListFilter(field_name='worker_days__dt', lookup_expr='in')

    employments__dt_from = QDateFilter(field_name='employments__dt_fired', lookup_expr='gte', or_isnull=True)
    employments__dt_to = QDateFilter(field_name='employments__dt_hired', lookup_expr='lte', or_isnull=True)

    id = QNumberFilter(field_name='id')
    id__in = QListFilter(field_name='id', lookup_expr='in')

    tabel_code = QCharFilter(field_name='tabel_code')
    tabel_code__in = QListFilter(field_name='tabel_code', lookup_expr='in')

    class Meta:
        model = Employee
        fields = []


class NotificationFilter(FilterSet):
    class Meta:
        model = Notification
        fields = ['worker_id', 'is_read']



class SubscribeFilter(FilterSet):
    shop_id = NumberFilter(field_name='employments__shop_id')

    class Meta:
        model = Subscribe
        fields = ('user_id', 'shop_id')


class ShopScheduleFilter(FilterSet):
    class Meta:
        model = ShopSchedule
        fields = {
            'dt': ['exact', 'lte', 'gte'],
            'type': ['exact', 'in'],
        }
