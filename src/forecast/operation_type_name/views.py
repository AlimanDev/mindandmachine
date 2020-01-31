import datetime

from rest_framework import serializers, viewsets
from rest_framework.response import Response
from src.util.utils import JsonResponse

from src.base.permissions import Permission
from src.forecast.models import OperationTypeName, OperationType

# Serializers define the API representation.
class OperationTypeNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationTypeName
        fields = ['id', 'name', 'code']


class OperationTypeNameViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/work_type_name/
    :return [   {"id": 1, "title": Abcd, "code": "1"}
        {"id": 2, "title": Aaaa, "code": "2"}, ...
    ]

    GET /rest_api/work_type_name/6/
    :return {"id": 6, ...}


    POST /rest_api/work_type_name/, {"title": 'abcd'}
    :return {"id": 10, ...}

    PUT /rest_api/work_type_name/6, {"title": 'abcd'}
    :return {"id": 6, ...}

    """
    permission_classes = [Permission]
    serializer_class = OperationTypeNameSerializer
    queryset = OperationTypeName.objects.all()
    
    def create(self, request):
        data = OperationTypeNameSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        code = data.validated_data.get('code')
        name = data.validated_data.get('name')
        if code is not '' and not code:
            return JsonResponse.value_error('Code should be defined')
        if (OperationTypeName.objects.filter(code=code).exists() and code is not '') or \
            OperationTypeName.objects.filter(name=name).exists():
            return JsonResponse.already_exists_error('Operation type name with such code or name already exists')
        data.save()

        return Response(data.data, status=201)

    def update(self, request, pk=None):
        operation_type_name = OperationTypeName.objects.get(pk=pk)
        data = OperationTypeNameSerializer(instance=operation_type_name, data=request.data)
        data.is_valid(raise_exception=True)
        code = data.validated_data.get('code')
        name = data.validated_data.get('name')
        if (OperationTypeName.objects.filter(code=code).exists() and code is not '') or \
            OperationTypeName.objects.filter(name=name).exists():
            return JsonResponse.already_exists_error('Operation type name with such code or name already exists')
        data.save()

        return Response(data.data)

    def destroy(self, request, pk=None):
        operation_type_name = OperationTypeName.objects.get(pk=pk)
        dt_now = datetime.datetime.now()
        operation_type_name.dttm_deleted = dt_now
        operation_type_name.save()
        OperationType.objects.filter(operation_type_name__id=pk).update(
            dttm_deleted=dt_now
        )
        return Response(OperationTypeNameSerializer(operation_type_name).data)
