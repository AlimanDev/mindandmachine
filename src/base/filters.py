from django.db.models import Q
from django_filters.rest_framework import FilterSet, DateFilter, NumberFilter, CharFilter

from src.base.models import  Employment, User, Notification, Subscribe


class BaseActiveNamedModelFilter(FilterSet):
    name = CharFilter(field_name='name', lookup_expr='exact')
    name__in = CharFilter(field_name='name', method='field_in')
    code = CharFilter(field_name='code', lookup_expr='exact')
    code__in = CharFilter(field_name='code', method='field_in')
    id__in = NumberFilter(field_name='id', method='field_in')

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

    def gte_or_null(self, queryset, name, value):
        return queryset.filter(
            Q(dt_fired__gte=value) | Q(dt_fired__isnull=True)
        )
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
    shop_id__in = CharFilter(method='shop_id_in')
    shop_code = CharFilter(field_name='employments__shop__code', label='Код магазина')
    shop_code__in = CharFilter(method='shop_code_in')
    last_name = CharFilter(field_name='last_name', lookup_expr='icontains')

    def shop_id_in(self, queryset, name, value):
        return queryset.filter(
            employments__shop_id__in=value.split(','),
        )

    def shop_code_in(self, queryset, name, value):
        return queryset.filter(
            employments__shop_code__in=value.split(','),
        )

    class Meta:
        model = User
        fields = {
            'id':['exact', 'in'],
            'tabel_code':['exact', 'in'],
            'username':['exact', 'in'],
            'last_name':['in',],
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
        fields = [ 'user_id', 'shop_id']
