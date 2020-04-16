from django.db.models import Q
from django_filters.rest_framework import FilterSet, DateFilter, NumberFilter

from src.base.models import  Employment, User, Notification, Subscribe


class EmploymentFilter(FilterSet):
    dt_from = DateFilter(method='gte_or_null')
    dt_to = DateFilter(field_name='dt_hired', lookup_expr='lte', label='Окончание периода')

    def gte_or_null(self, queryset, name, value):
        return queryset.filter(
            Q(dt_fired__gte=value) | Q(dt_fired__isnull=True)
        )
    class Meta:
        model = Employment
        fields = {
            'id':['in'],
            'shop_id': ['exact'],
            'user_id': ['exact', 'in'],

        }


class EmploymentRequiredFilter(FilterSet):
    dt_from = DateFilter(method='gte_or_null', required=True)
    dt_to = DateFilter(field_name='dt_hired', lookup_expr='lte', label='Окончание периода', required=True)
    shop_id = NumberFilter(required=True)

    def gte_or_null(self, queryset, name, value):
        return queryset.filter(
            Q(dt_fired__gte=value) | Q(dt_fired__isnull=True)
        )
    class Meta:
        model = Employment
        fields = {
            'shop_id': ['exact'],
            'user_id': ['exact', 'in'],
        }


class UserFilter(FilterSet):
    shop_id=NumberFilter(field_name='employments__shop_id')
    class Meta:
        model = User
        fields = {
            'id':['exact', 'in'],
            'shop_id': ['exact'],
        }


class NotificationFilter(FilterSet):
    class Meta:
        model = Notification
        fields = ['worker_id', 'is_read']


class SubscribeFilter(FilterSet):
    shop_id=NumberFilter(field_name='employments__shop_id')
    class Meta:
        model = Subscribe
        fields = [ 'user_id', 'shop_id']
