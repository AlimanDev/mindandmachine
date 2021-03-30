from src.base.filters import BaseActiveNamedModelFilter
from django_filters.rest_framework import NumberFilter, CharFilter


class TickPointFilterSet(BaseActiveNamedModelFilter):
    shop_id = NumberFilter(field_name='shop_id', lookup_expr='exact')
    shop_id__in = CharFilter(field_name='shop_id', method='field_in')
