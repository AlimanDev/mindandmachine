from django_filters.rest_framework import FilterSet, OrderingFilter
from ..models import Timesheet


class TimesheetFilter(FilterSet):
    order_by = OrderingFilter(fields=('dt',))

    class Meta:
        model = Timesheet
        fields = {
            'dt': ['exact', 'gte', 'lte'],
            'employee_id': ['exact', 'in'],
            'employee__tabel_code': ['exact', 'in'],
            'shop_id': ['exact', 'in'],
            'fact_timesheet_source': ['exact', 'in'],
        }
