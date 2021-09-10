from src.base.permissions import Permission
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from src.reports.utils.pivot_tabel import PlanAndFactPivotTabel
from src.reports.serializers import PivotTabelSerializer

class ReportsViewSet(ViewSet):
    permission_classes = [Permission]

    @action(detail=False, methods=['get'])
    def pivot_tabel(self, request):
        def _add_filter(data, filters, name, query_name):
            if name in data:
                filters[query_name] = data[name]
            return filters
        data = PivotTabelSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        filters = {
            'dt__gte': data['dt_from'],
            'dt__lte': data['dt_to'],
        }
        filters = _add_filter(data, filters, 'shop_ids', 'shop_id__in')
        filters = _add_filter(data, filters, 'employee_ids', 'employee_id__in')
        filters = _add_filter(data, filters, 'user_ids', 'worker_id__in')
        filters = _add_filter(data, filters, 'is_vacancy', 'is_vacancy')
        filters = _add_filter(data, filters, 'is_outsource', 'is_outsource')
        filters = _add_filter(data, filters, 'network_ids', 'worker__network_id__in')
        filters = _add_filter(data, filters, 'work_type_name', 'work_type_name__in')


        pt = PlanAndFactPivotTabel()
        return pt.get_response(**filters)
