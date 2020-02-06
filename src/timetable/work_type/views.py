import datetime

from rest_framework import serializers, viewsets
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.util.utils import JsonResponse
from src.base.permissions import FilteredListPermission
from src.timetable.models import WorkType, WorkTypeName
from django.db.models import Q, F
from src.timetable.work_type_name.views import WorkTypeNameSerializer

# Serializers define the API representation.
class WorkTypeSerializer(serializers.ModelSerializer):
    work_type_name = WorkTypeNameSerializer(required=False)
    code = serializers.CharField(required=False, write_only=True)
    shop_id = serializers.IntegerField(required=False)
    work_type_name_id = serializers.IntegerField(required=False, write_only=True)
    class Meta:
        model = WorkType
        fields = ['id', 'priority', 'dttm_last_update_queue', 'min_workers_amount', 'max_workers_amount',\
             'probability', 'prior_weight', 'shop_id', 'code', 'work_type_name_id', 'work_type_name']


class WorkTypeFilter(FilterSet):
    class Meta:
        model = WorkType
        fields = {
            'shop_id':['exact',],
        }


class WorkTypeViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/work_type/?shop_id=6
    :return [{"id":2, ...},{"id":3, ...}]

    GET /rest_api/work_type/
    :return [   {"id": 1, ...}
        {"id": 2, ...}, ...
    ]

    GET /rest_api/work_type/6/
    :return {"id": 6, ...}


    POST /rest_api/work_type/, {"title": 'abcd'}
    :return {"id": 10, ...}

    PUT /rest_api/work_type/6, {"title": 'abcd'}
    :return {"id": 6, ...}

    """
    permission_classes = [FilteredListPermission]
    serializer_class = WorkTypeSerializer
    filterset_class = WorkTypeFilter

    def get_queryset(self):
        return self.filter_queryset(
            WorkType.objects.select_related('work_type_name').filter(dttm_deleted__isnull=True)
        )

