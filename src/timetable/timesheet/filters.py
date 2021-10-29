from django_filters.rest_framework import FilterSet, OrderingFilter
from src.util.drf.filters import ListFilter


from ..models import TimesheetItem


class TimesheetFilter(FilterSet):
    order_by = OrderingFilter(fields=('dt',))
    employee_id__in = ListFilter(field_name='employee_id', lookup_expr='in')

    class Meta:
        model = TimesheetItem
        fields = {
            'dt': ['exact', 'gte', 'lte', 'in'],
            'employee_id': ['exact'],
            'employee__tabel_code': ['exact', 'in'],
            'shop_id': ['exact', 'in'],
            'shop__code': ['exact', 'in'],
            'position_id': ['exact', 'in'],
            'position__code': ['exact', 'in'],
            'work_type_name_id': ['exact', 'in'],
            'work_type_name__code': ['exact', 'in'],
            'source': ['exact', 'in'],
        }
