import datetime

from rest_framework import serializers, viewsets, permissions
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.base.models import WorkerPosition

# Serializers define the API representation.
class WorkerPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerPosition
        fields = ['id', 'name',]


class WorkerPositionViewSet(viewsets.ReadOnlyModelViewSet):
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
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WorkerPositionSerializer
    queryset = WorkerPosition.objects.filter(dttm_deleted__isnull=True)
