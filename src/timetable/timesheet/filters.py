from django_filters.rest_framework import FilterSet, OrderingFilter
from src.util.drf.filters import ListFilter


from ..models import Timesheet


class TimesheetFilter(FilterSet):
    order_by = OrderingFilter(fields=('dt',))
    employee_id__in = ListFilter(method='filter_employee_id__in')

    def filter_employee_id__in(self, queryset, name, value):
        if value:
            value = value.split(',')
            return queryset.filter(employee_id__in=value)
        return queryset

    class Meta:
        model = Timesheet
        fields = {
            'dt': ['exact', 'gte', 'lte', 'in'],
            'employee_id': ['exact'],
            'employee__tabel_code': ['exact', 'in'],
            'shop_id': ['exact', 'in'],
            'shop__code': ['exact', 'in'],
            'fact_timesheet_source': ['exact', 'in'],
        }
