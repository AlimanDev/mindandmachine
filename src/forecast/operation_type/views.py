import datetime

from rest_framework import serializers, viewsets
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.util.utils import JsonResponse
from src.base.permissions import Permission, FilteredListPermission
from src.forecast.models import OperationType, OperationTypeName
from django.db.models import Q, F
from src.main.other.notification.utils import send_notification


# Serializers define the API representation.
class OperationTypeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    work_type_id = serializers.IntegerField(required=False)
    operation_type_name_id = serializers.IntegerField(required=False)
    class Meta:
        model = OperationType
        fields = ['id', 'work_type_id', 'speed_coef', 'do_forecast', 'name', 'code', 'operation_type_name_id']


class OperationTypeFilter(FilterSet):
    class Meta:
        model = OperationType
        fields = {
            'work_type__shop_id':['exact',],
            'work_type_id':['exact', 'in',],
            'id':['exact', 'in',],
        }


class OperationTypeViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/operation_type/?shop_id=6
    :return [{"id":2, ...},{"id":3, ...}]

    GET /rest_api/operation_type/
    :return [   {"id": 1, ...}
        {"id": 2, ...}, ...
    ]

    GET /rest_api/operation_type/6/
    :return {"id": 6, ...}


    POST /rest_api/operation_type/, {"name": 'abcd'}
    :return {"id": 10, ...}

    PUT /rest_api/operation_type/6, {"name": 'abcd'}
    :return {"id": 6, ...}

    """
    permission_classes = [Permission, FilteredListPermission]
    serializer_class = OperationTypeSerializer
    filterset_class = OperationTypeFilter

    def get_queryset(self):
        return self.filter_queryset(OperationType.objects.select_related('operation_type_name').all())

    def create(self, request):
        data = OperationTypeSerializer(data=request.data)

        if not data.is_valid():
            return JsonResponse.value_error(data.error_messages)
        if not data.validated_data.get('work_type_id'):
            return JsonResponse.value_error('Work type id should be defined')
        if not (data.validated_data.get('operation_type_name_id') or data.validated_data.get('code')):
            return JsonResponse.value_error('ID or code of operation type should be defined')
        

        if OperationType.objects.filter(
            Q(operation_type_name_id=data.validated_data.get('operation_type_name_id')) | Q(operation_type_name__code=data.validated_data.get('code')), 
            work_type_id=data.validated_data.get('work_type_id'), 
            dttm_deleted__isnull=True,
        ).count() > 0:
            return JsonResponse.already_exists_error('Такой тип операций в данном магазине уже существует')

        try:
            operation_type_name = OperationTypeName.objects.get(Q(id=data.validated_data.get('operation_type_name_id')) | Q(code=data.validated_data.get('code')))
        except:
            return JsonResponse.does_not_exists_error('Не существует такого названия для типа операций.')

        data.validated_data.pop('code', None)
        data.validated_data['operation_type_name'] = operation_type_name
        data.save()
        json_data = data.data.copy()
        json_data['name'] = operation_type_name.name

        send_notification('C', data.instance, sender=request.user)

        return Response(json_data, status=201)

    def update(self, request, pk=None):
        operation_type = OperationType.objects.get(pk=pk)
        data = OperationTypeSerializer(instance=operation_type, data=request.data)
        if not data.is_valid():
            return JsonResponse.value_error(data.error_messages)

        if data.validated_data.get('operation_type_name_id') or data.validated_data.get('code'):
            try:
                operation_type_name = OperationTypeName.objects.get(Q(id=data.validated_data.get('operation_type_name_id')) | Q(code=data.validated_data.get('code')))
            except:
                return JsonResponse.does_not_exists_error('Не существует такого названия для типа операций.')
            data.validated_data.pop('code', None)
            data.validated_data['operation_type_name'] = operation_type_name

        try:
            data.save()
        except ValueError:
            return JsonResponse.value_error('Error upon saving operation type instance. One of the parameters is invalid')
   
        data = OperationTypeSerializer(instance=data.instance).data.copy()
        data['name'] = operation_type_name.name

        return Response(data)

    def destroy(self, request, pk=None):
        operation_type = OperationType.objects.get(pk=pk)

        operation_type.dttm_deleted = datetime.datetime.now()
        operation_type.save()

        send_notification('D', operation_type, sender=request.user)
    
        return Response(OperationTypeSerializer(operation_type).data)

    def list(self, request):
        return Response(OperationTypeSerializer(self.get_queryset().annotate(name=F('operation_type_name__name')), many=True).data)

    def retrieve(self, request, pk=None):
        return Response(OperationTypeSerializer(self.get_queryset().annotate(name=F('operation_type_name__name')).get(pk=pk)).data)
