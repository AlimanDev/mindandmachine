from rest_framework import serializers, viewsets
from django_filters.rest_framework import FilterSet
from src.base.permissions import Permission
from src.timetable.models import WorkType,WorkTypeName
from src.timetable.work_type_name.views import WorkTypeNameSerializer
from rest_framework.decorators import action
from src.timetable.work_type.utils import get_efficiency
from src.conf.djconfig import QOS_DATE_FORMAT
from rest_framework.validators import UniqueTogetherValidator
from rest_framework.response import Response


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
        validators = [
            UniqueTogetherValidator(
                queryset=WorkType.objects.filter(dttm_deleted__isnull=True),
                fields=['shop_id', 'work_type_name_id'],
            ),
        ]
    def is_valid(self, *args, **kwargs):
        if self.initial_data.get('code', False):
            self.initial_data['work_type_name_id'] = WorkTypeName.objects.get(code=self.initial_data.get('code')).id
        super().is_valid(*args, **kwargs)

class EfficiencySerializer(serializers.Serializer):
    from_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    to_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    work_type_ids = serializers.ListField(allow_empty=True, child=serializers.IntegerField(), required=False, default=[])
    shop_id = serializers.IntegerField()

    def is_valid(self, *args, **kwargs):
        super(EfficiencySerializer, self).is_valid(*args, **kwargs)

        if self.validated_data['from_dt'] > self.validated_data['to_dt']:
            raise serializers.ValidationError('dt_from have to be less or equal than dt_to')


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
    permission_classes = [Permission]
    serializer_class = WorkTypeSerializer
    filterset_class = WorkTypeFilter

    def get_queryset(self):
        return self.filter_queryset(
            WorkType.objects.select_related('work_type_name').filter(dttm_deleted__isnull=True)
        )

    @action(detail=False, methods=['get'])
    def efficiency(self, request):
        data = EfficiencySerializer(data=request.query_params)

        data.is_valid(raise_exception=True)

        return Response(get_efficiency(data.validated_data.get('shop_id'), data.validated_data), status=200)