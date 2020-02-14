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

    GET /rest_api/work_type/
    :params
        shop_id: int, required=False
    :return [
        {
            "id": 2,
            "priority": 23,
            "dttm_last_update_queue": None,
            "min_workers_amount": 2,
            "max_workers_amount": 10,
            "probability": 2.0,
            "prior_weigth": 1.0,
            "shop_id": 1,
            "work_type_name":{
                "id": 1,
                "name": "Work type",
                "code": "1",
            }
        },
        ...
    ]


    GET /rest_api/work_type/6/
    :return {
        "id": 6,
        "priority": 23,
        "dttm_last_update_queue": None,
        "min_workers_amount": 2,
        "max_workers_amount": 10,
        "probability": 2.0,
        "prior_weigth": 1.0,
        "shop_id": 1,
        "work_type_name":{
            "id": 1,
            "name": "Work type",
            "code": "1",
        }
    }


    POST /rest_api/work_type/
    :params
        priority: int, required=False
        min_workers_amount: int, required=False
        max_workers_amount: int, required=False
        probability: float, required=Fasle
        prior_weigth: float, required=False
        shop_id: int, required=True
        code: str, required=False
        work_type_name_id: int, required=False
    :return 
        code 201
        {
            "id": 6,
            "priority": 23,
            "dttm_last_update_queue": None,
            "min_workers_amount": 2,
            "max_workers_amount": 10,
            "probability": 2.0,
            "prior_weigth": 1.0,
            "shop_id": 1,
            "work_type_name":{
                "id": 1,
                "name": "Work type",
                "code": "1",
            }
        }


    PUT /rest_api/work_type/6/
    :params
        priority: int, required=False
        min_workers_amount: int, required=False
        max_workers_amount: int, required=False
        probability: float, required=Fasle
        prior_weigth: float, required=False
        shop_id: int, required=True
        code: str, required=False
        work_type_name_id: int, required=False
    :return {
        "id": 6,
        "priority": 23,
        "dttm_last_update_queue": None,
        "min_workers_amount": 2,
        "max_workers_amount": 10,
        "probability": 2.0,
        "prior_weigth": 1.0,
        "shop_id": 1,
        "work_type_name":{
            "id": 1,
            "name": "Work type",
            "code": "1",
        }
    }


    DELETE /rest_api/work_type/6/
    :return
        code 204

    """
    permission_classes = [FilteredListPermission]
    serializer_class = WorkTypeSerializer
    filterset_class = WorkTypeFilter

    def get_queryset(self):
        return self.filter_queryset(
            WorkType.objects.select_related('work_type_name').filter(dttm_deleted__isnull=True)
        )

