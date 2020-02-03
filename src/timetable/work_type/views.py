import datetime

from rest_framework import serializers, viewsets
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.util.utils import JsonResponse
from src.base.permissions import FilteredListPermission
from src.timetable.models import WorkType, Cashbox, WorkTypeName
from django.db.models import Q, F
from src.main.other.notification.utils import send_notification


# Serializers define the API representation.
class WorkTypeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    shop_id = serializers.IntegerField(required=False)
    work_type_name_id = serializers.IntegerField(required=False)
    class Meta:
        model = WorkType
        fields = ['id', 'priority', 'dttm_last_update_queue', 'min_workers_amount', 'max_workers_amount',\
             'probability', 'prior_weight', 'shop_id', 'name', 'code', 'work_type_name_id']


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
    # queryset = self.filter_queryset(WorkType.objects.select_related('work_type_name').all())

    def get_queryset(self):
        return self.filter_queryset(WorkType.objects.select_related('work_type_name').all())

    def create(self, request):
        data = WorkTypeSerializer(data=request.data)

        if not data.is_valid():
            return JsonResponse.value_error(data.error_messages)
        if not data.validated_data.get('shop_id'):
            return JsonResponse.value_error('Shop id should be defined')
        if not (data.validated_data.get('work_type_name_id') or data.validated_data.get('code')):
            return JsonResponse.value_error('ID or code of work type should be defined')

        if WorkType.objects.filter(
            Q(work_type_name_id=data.validated_data.get('work_type_name_id')) | Q(work_type_name__code=data.validated_data.get('code')), 
            shop_id=data.validated_data.get('shop_id'), 
            dttm_deleted__isnull=True,
        ).count() > 0:
            return JsonResponse.already_exists_error('Такой тип работ в данном магазине уже существует')

        try:
            work_type_name = WorkTypeName.objects.get(Q(id=data.validated_data.get('work_type_name_id')) | Q(code=data.validated_data.get('code')))
        except:
            return JsonResponse.does_not_exists_error('Не существует такого названия для типа работ.')

        data.validated_data.pop('code', None)
        data.validated_data['work_type_name'] = work_type_name
        data.save()
        json_data = data.data.copy()
        json_data['name'] = work_type_name.name

        send_notification('C', data.instance, sender=request.user)

        return Response(json_data, status=201)

    def update(self, request, pk=None):
        work_type = WorkType.objects.get(pk=pk)
        data = WorkTypeSerializer(instance=work_type, data=request.data)
        if not data.is_valid():
            return JsonResponse.value_error(data.error_messages)


        if data.validated_data.get('name') or data.validated_data.get('code'):
            try:
                work_type_name = WorkTypeName.objects.get(Q(name=data.validated_data.get('name')) | Q(code=data.validated_data.get('code')))
            except:
                return JsonResponse.does_not_exists_error('Не существует такого названия для типа работ.')
            data.validated_data.pop('name', None)
            data.validated_data.pop('code', None)
            data.validated_data['work_type_name'] = work_type_name

        try:
            data.save()
        except ValueError:
            return JsonResponse.value_error('Error upon saving work type instance. One of the parameters is invalid')
   
        data = WorkTypeSerializer(instance=data.instance).data.copy()
        data['name'] = work_type_name.name

        return Response(data)

    def destroy(self, request, pk=None):
        work_type = WorkType.objects.get(pk=pk)

        attached_cashboxes = Cashbox.objects.filter(type=work_type, dttm_deleted__isnull=True)

        if attached_cashboxes.count() > 0:
            return JsonResponse.internal_error('there are cashboxes on this type')

        work_type.dttm_deleted = datetime.datetime.now()
        work_type.save()

        send_notification('D', work_type, sender=request.user)
    
        return Response(WorkTypeSerializer(work_type).data)

    def list(self, request):
        return Response(WorkTypeSerializer(self.get_queryset().annotate(name=F('work_type_name__name')), many=True).data)

    def retrieve(self, request, pk=None):
        return Response(WorkTypeSerializer(self.get_queryset().annotate(name=F('work_type_name__name')).get(pk=pk)).data)
