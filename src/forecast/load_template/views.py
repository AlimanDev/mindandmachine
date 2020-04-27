from rest_framework import serializers, viewsets, status, permissions
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from django_filters import CharFilter
from src.forecast.models import LoadTemplate
from src.forecast.load_template.utils import create_load_template_for_shop
from src.celery.tasks import calculate_shops_load, apply_load_template_to_shops
from rest_framework.decorators import action
from src.conf.djconfig import QOS_DATE_FORMAT
from src.forecast.operation_type_template.views import OperationTypeTemplateSerializer
from src.base.exceptions import MessageError
from celery import exceptions as celery_exceptions


# Serializers define the API representation.
class LoadTemplateSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(write_only=True, required=False)
    operation_type_templates = OperationTypeTemplateSerializer(many=True, read_only=True)
    class Meta:
        model = LoadTemplate
        fields = ['id', 'name', 'shop_id', 'operation_type_templates']


class LoadTemplateSpecSerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT, write_only=True)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT, write_only=True, required=False)
    id = serializers.IntegerField(write_only=True)
    shop_id = serializers.IntegerField(write_only=True, required=False)


class LoadTemplateFilter(FilterSet):
    name = CharFilter(field_name='name', lookup_expr='icontains')

    class Meta:
        model = LoadTemplate
        fields = {
            'id': ['exact', ]
        }


class LoadTemplateViewSet(viewsets.ModelViewSet):
    """
    GET /rest_api/load_template/
    :params
        name: str, required=False
    :return [
        {
           "id": 1,
           "name": "Load template",
           "operation_type_templates":[
               {
                    'id': 1, 
                    'load_template_id': 1, 
                    'work_type_name_id': None, 
                    'do_forecast': 'F', 
                    'operation_type_name': {
                        'id': 1, 
                        'name': 'Кассы', 
                        'code': None
                    },
               },
               ...
           ],
        },
        ...
    ]


    GET /rest_api/load_template/1/
    :return {
       "id": 1,
       "name": "Load template",
       "operation_type_templates":[
           {
                'id': 1, 
                'load_template_id': 1, 
                'work_type_name_id': None, 
                'do_forecast': 'F', 
                'operation_type_name': {
                    'id': 1, 
                    'name': 'Кассы', 
                    'code': None
                },
           },
           ...
       ],
    }


    POST /rest_api/load_template/
    :params
        name: str, required=True,
        shop_id: int, required=False, 
        (shop_id спользуется чтобы создать load_template
        от магазина см. описание create_load_template_for_shop)
    :return 
        code=201
    {
        "id": 1,
        "name": "Load template",
        "operation_type_templates":[],
    }

    PUT /rest_api/load_template/1/
    :params
        name: str, required=True
    :return
        code=200


    DELETE /rest_api/load_template/1/
    :return
        code=204
   

    POST /rest_api/load_template/apply/
    применяет шаблон нагрузки к магазину
    см. описание apply_load_template
    :params
        dt_from: QOS_DATE_FORMAT, required=True
        id: int (load_template_id), required=True
        shop_id: int, required=False
        (если указан shop_id будет применён к этому магазину
        в противном случае ко всем магазинам, привязанным к
        данному load_template)
    :return
        code=200

    POST /rest_api/load_template/calculate/
    выполняет расчет нагрузки магазина(-ов)
    см. описание calculate_shop_load
    :params
        dt_from: QOS_DATE_FORMAT, required=True
        dt_to: QOS_DATE_FORMAT, required=True
        id: int (load_template_id), required=True
        shop_id: int, required=False
        (если указан shop_id будет расчитан этот магазин
        в противном случае все магазины, привязанные к
        данному load_template)
    :return
        code=200


    """
    permission_classes = [permissions.IsAdminUser]
    filterset_class = LoadTemplateFilter
    serializer_class = LoadTemplateSerializer

    def get_queryset(self):
        return self.filter_queryset(LoadTemplate.objects.all())
    

    def create(self, request):
        data = LoadTemplateSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        shop_id = data.validated_data.get('shop_id')
        
        if shop_id:
            load_template = create_load_template_for_shop(shop_id)
        else:
            load_template = LoadTemplate.objects.create(
                name=data.validated_data.get('name'),
            )

        return Response(LoadTemplateSerializer(instance=load_template).data, status=201)


    @action(detail=False, methods=['post'])
    def apply(self, request):
        data = LoadTemplateSpecSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shop_id = data.validated_data.get('shop_id')
        load_template_id = data.validated_data.get('id')
        dt_from = data.validated_data.get('dt_from')
        try:
            apply_load_template_to_shops.delay(request.user, load_template_id, dt_from, shop_id=shop_id)
        except celery_exceptions.OperationalError:
            apply_load_template_to_shops(request.user, load_template_id, dt_from, shop_id=shop_id)
        
        return Response(status=200)


    @action(detail=False, methods=['post'])
    def calculate(self, request):
        data = LoadTemplateSpecSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shop_id = data.validated_data.get('shop_id')
        load_template_id = data.validated_data.get('id')
        dt_from = data.validated_data.get('dt_from')
        dt_to = data.validated_data.get('dt_to')
        if not dt_to:
            raise MessageError(code="dt_to_required", lang=request.user.lang)
        try:
            calculate_shops_load.delay(request.user, load_template_id, dt_from, dt_to, shop_id=shop_id)
        except celery_exceptions.OperationalError:
            calculate_shops_load(request.user, load_template_id, dt_from, dt_to, shop_id=shop_id)

        return Response(200)


    def destroy(self, request, pk=None):
        load_template = LoadTemplate.objects.get(pk=pk)
        if load_template.shops.exists():
            raise MessageError(code="load_template_attached_shops", lang=requset.user.lang)
        load_template.delete()

        return Response(status=204)
