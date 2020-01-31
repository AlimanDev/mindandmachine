import datetime

from rest_framework import serializers, viewsets
from rest_framework.response import Response
from src.util.utils import JsonResponse

from src.base.permissions import Permission, FilteredListPermission
from src.timetable.models import WorkTypeName, WorkType


# Serializers define the API representation.
class WorkTypeNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkTypeName
        fields = ['id', 'name', 'code']


class WorkTypeNameViewSet(viewsets.ModelViewSet):
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
    serializer_class = WorkTypeNameSerializer
    queryset = WorkTypeName.objects.all()
    
    def create(self, requset):
        data = WorkTypeNameSerializer(data=requset.data)
        data.is_valid(raise_exception=True)
        code = data.validated_data.get('code')
        name = data.validated_data.get('name')

        if not code and code is not '':
            return JsonResponse.value_error('Code should be defined')
        if (WorkTypeName.objects.filter(code=code).exists() and code is not '') or \
            WorkTypeName.objects.filter(name=name).exists():
            return JsonResponse.already_exists_error('Work type name with such code or name already exists')
        data.save()

        return Response(data.data, status=201)

    def update(self, request, pk=None):
        work_type_name = WorkTypeName.objects.get(pk=pk)
        data = WorkTypeNameSerializer(instance=work_type_name, data=request.data)
        data.is_valid(raise_exception=True)
        code = data.validated_data.get('code')
        name = data.validated_data.get('name')
        if (WorkTypeName.objects.filter(code=code).exists() and code is not '') or \
            WorkTypeName.objects.filter(name=name).exists():
            return JsonResponse.already_exists_error('Work type name with such code or name already exists')
        data.save()

        return Response(data.data)

    def destroy(self, request, pk=None):
        work_type_name = WorkTypeName.objects.get(pk=pk)
        dt_now = datetime.datetime.now()
        work_type_name.dttm_deleted = dt_now
        work_type_name.save()
        WorkType.objects.filter(work_type_name__id=work_type_name.id).update(
            dttm_deleted=dt_now,
        )
        return Response(WorkTypeNameSerializer(work_type_name).data)
