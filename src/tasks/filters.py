from django_filters.rest_framework import NumberFilter

from src.base.filters import BaseActiveNamedModelFilter
from src.util.drf.filters import ListFilter
from .models import Task


class TaskFilter(BaseActiveNamedModelFilter):
    shop_id = NumberFilter(field_name='operation_type__shop_id')
    shop_id__in = ListFilter(field_name='operation_type__shop_id', lookup_expr='in')

    employee_id = NumberFilter(field_name='employee_id')
    employee_id__in = ListFilter(field_name='employee_id', lookup_expr='in')

    class Meta:
        model = Task
        fields = {
            'dt': ['gte', 'lte']
        }
