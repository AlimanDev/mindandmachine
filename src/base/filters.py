from django.db.models import Q
from django_filters.rest_framework import FilterSet, DateFilter

from src.base.models import  Employment, User


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


class UserFilter(FilterSet):
    class Meta:
        model = User
        fields = {
            'id':['exact', 'in'],
            'employments__shop_id': ['exact'],
        }
