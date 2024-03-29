from django_filters.rest_framework import NumberFilter

from src.apps.base.filters import BaseActiveNamedModelFilter
from src.common.drf.filters import ListFilter


class TickPointFilterSet(BaseActiveNamedModelFilter):
    shop_id = NumberFilter(field_name='shop_id', lookup_expr='exact')
    shop_id__in = ListFilter(field_name='shop_id', lookup_expr='in')
