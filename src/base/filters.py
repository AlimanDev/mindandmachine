from django.db.models import Q
from django_filters.rest_framework import FilterSet, DateFilter, NumberFilter, CharFilter, BooleanFilter, OrderingFilter

from src.base.models import Employment, User, Notification, Subscribe, Shop, ShopSchedule


class BaseActiveNamedModelFilter(FilterSet):
    name = CharFilter(field_name='name', lookup_expr='icontains')
    name__in = CharFilter(field_name='name', method='field_in')
    code = CharFilter(field_name='code', lookup_expr='exact')
    code__in = CharFilter(field_name='code', method='field_in')
    id__in = CharFilter(field_name='id', method='field_in')

    def field_in(self, queryset, name, value):
        filt = {
            f'{name}__in': value.split(',')
        }
        return queryset.filter(**filt)


class EmploymentFilter(FilterSet):
    dt_from = DateFilter(method='gte_or_null')
    dt_to = DateFilter(field_name='dt_hired', lookup_expr='lte', label='Окончание периода')
    shop_code = CharFilter(field_name='shop__code', label='Код магазина')
    username = CharFilter(field_name='user__username', label='Логин сотрудника')
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
                            user=self.request.user,
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
            'shop_code': ['exact', 'in'],
            'user_id': ['exact', 'in'],
            'username': ['exact', 'in'],
            'is_visible': ['exact',]
        }


class UserFilter(FilterSet):
    shop_id = NumberFilter(field_name='employments__shop_id')
    shop_id__in = CharFilter(field_name='employments__shop_id', method='field_in')
    shop_code = CharFilter(field_name='employments__shop__code', label='Код магазина')
    shop_code__in = CharFilter(field_name='employments__shop__code', method='field_in')
    last_name = CharFilter(field_name='last_name', lookup_expr='icontains')
    first_name = CharFilter(field_name='first_name', lookup_expr='icontains')
    position_id__in = CharFilter(field_name='employments__position_id', method='field_in')
    work_type_id__in = CharFilter(field_name='employments__work_types__work_type__work_type_name_id', method='field_in')
    worker_day_type__in = CharFilter(field_name='worker_day__type', method='field_in')
    worker_day_dt__in = CharFilter(field_name='worker_day__dt', method='field_in')

    employments__dt_from = DateFilter(method='employments_dt_from')
    employments__dt_to = DateFilter(method='employments_dt_to')

    def employments_dt_from(self, queryset, name, value):
        return queryset.filter(
            Q(employments__dt_fired__gte=value) | Q(employments__dt_fired__isnull=True),
        )

    def employments_dt_to(self, queryset, name, value):
        return queryset.filter(
            Q(employments__dt_hired__lte=value) | Q(employments__dt_hired__isnull=True),
        )

    def shop_id_in(self, queryset, name, value):
        return queryset.filter(
            employments__shop_id__in=value.split(','),
        )

    def field_in(self, queryset, name, value):
        filt = {
            f'{name}__in': value.split(',')
        }
        return queryset.filter(**filt)

    class Meta:
        model = User
        fields = {
            'id': ['exact', 'in'],
            'tabel_code': ['exact', 'in'],
            'username': ['exact', 'in'],
            'last_name': ['in', ],
            'shop_id': ['exact', 'in'],
            'shop_code': ['exact'],
        }


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
