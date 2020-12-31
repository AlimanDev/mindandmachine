from celery import exceptions as celery_exceptions

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination
from django_filters.rest_framework import FilterSet
from django_filters import CharFilter


from src.forecast.models import LoadTemplate
from src.forecast.load_template.utils import create_load_template_for_shop, download_load_template, upload_load_template
from src.forecast.operation_type_template.views import OperationTypeTemplateSerializer

from src.celery.tasks import calculate_shops_load, apply_load_template_to_shops
from src.conf.djconfig import QOS_DATE_FORMAT
from src.base.exceptions import FieldError
from src.base.serializers import BaseNetworkSerializer
from src.base.models import Shop
from src.base.permissions import Permission
from src.base.views_abstract import BaseModelViewSet

from django.db.models import Exists, OuterRef, Case, When, CharField, Value
from django.utils.translation import gettext_lazy as _
from src.util.upload import get_uploaded_file
from src.base.fields import CurrentUserNetwork

from drf_yasg.utils import swagger_auto_schema


# Serializers define the API representation.
class LoadTemplateSerializer(BaseNetworkSerializer):
    shop_id = serializers.IntegerField(write_only=True, required=False)
    operation_type_templates = OperationTypeTemplateSerializer(many=True, read_only=True)
    status = serializers.CharField(read_only=True)
    class Meta:
        model = LoadTemplate
        fields = ['id', 'name', 'shop_id', 'operation_type_templates', 'status', 'network_id', 'round_delta']


class LoadTemplateSpecSerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT, write_only=True, required=False)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT, write_only=True, required=False)
    id = serializers.IntegerField(write_only=True)
    shop_id = serializers.IntegerField(write_only=True, required=False)


class LoadTemplateUploadSerializer(serializers.Serializer):
    name = serializers.CharField()
    file = serializers.FileField()
    network_id = serializers.HiddenField(default=CurrentUserNetwork())

class LoadTemplateFilter(FilterSet):
    name = CharFilter(field_name='name', lookup_expr='icontains')

    class Meta:
        model = LoadTemplate
        fields = {
            'id': ['exact', ]
        }


class LoadTemplateViewSet(BaseModelViewSet):
    """
    GET /rest_api/load_template/
    :params
        name: str, required=False
    :return [
        {
           "id": 1,
           "name": "Load template",
           "status": "R", | "P" R - готов P - в процессе
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
       "type": "R",
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
        "type": "R",
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
    error_messages = {
        "load_template_attached_shops": _("Cannot delete template as it's used in demand calculations."),
        "required": _("This field ins required")
    }
    permission_classes = [Permission]
    filterset_class = LoadTemplateFilter
    serializer_class = LoadTemplateSerializer
    pagination_class = LimitOffsetPagination
    openapi_tags = ['LoadTemplate',]

    def get_queryset(self):
        return LoadTemplate.objects.filter(
            network_id=self.request.user.network_id
        ).annotate(
            error=Exists(Shop.objects.filter(load_template_id=OuterRef('pk'), load_template_status=Shop.LOAD_TEMPLATE_ERROR)),
            process=Exists(Shop.objects.filter(load_template_id=OuterRef('pk'), load_template_status=Shop.LOAD_TEMPLATE_PROCESS)),
        ).annotate(
            status=Case(
                When(error=True, then=Value('E')),
                When(process=True, then=Value('P')),
                default=Value('R'),
                output_field=CharField(),
            )
        )
    
    @swagger_auto_schema(operation_description='shop_id спользуется чтобы создать load_template от магазина см. описание create_load_template_for_shop')
    def create(self, request):
        data = LoadTemplateSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)

        shop_id = data.validated_data.get('shop_id')
        
        if shop_id:
            load_template = create_load_template_for_shop(shop_id, data.validated_data.get('network_id'))
        else:
            load_template = data.save()

        return Response(LoadTemplateSerializer(instance=load_template).data, status=201)


    @swagger_auto_schema(
        request_body=LoadTemplateSpecSerializer, 
        operation_description='''
        применяет шаблон нагрузки к магазину 
        см. описание src.forecast.utils.apply_load_template, 
        если указан shop_id будет применён к этому магазину
        в противном случае ко всем магазинам, привязанным к
        данному load_template
        ''',
        responses={200: 'empty response'},
    )
    @action(detail=False, methods=['post'])
    def apply(self, request):
        data = LoadTemplateSpecSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shop_id = data.validated_data.get('shop_id')
        load_template_id = data.validated_data.get('id')
        dt_from = data.validated_data.get('dt_from')
        try:
            apply_load_template_to_shops.delay(load_template_id, dt_from, shop_id=shop_id)
        except celery_exceptions.OperationalError:
            apply_load_template_to_shops(load_template_id, dt_from, shop_id=shop_id)
        
        return Response(status=200)


    @swagger_auto_schema(
        request_body=LoadTemplateSpecSerializer, 
        operation_description='''
        готовит запрос для расчёта нагрузки и отправляет его на алгоритмы,
        если указан shop_id будет расчитан этот магазин
        в противном случае все магазины, привязанные к
        данному load_template
        ''',
        responses={200: 'empty response'},
    )
    @action(detail=False, methods=['post'])
    def calculate(self, request):
        data = LoadTemplateSpecSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shop_id = data.validated_data.get('shop_id')
        load_template_id = data.validated_data.get('id')
        dt_from = data.validated_data.get('dt_from')
        dt_to = data.validated_data.get('dt_to')
        if not dt_to:
            raise ValidationError(
                {'dt_to': self.error_messages['required']}
            )
        try:
            calculate_shops_load.delay(load_template_id, dt_from, dt_to, shop_id=shop_id)
        except celery_exceptions.OperationalError:
            calculate_shops_load(load_template_id, dt_from, dt_to, shop_id=shop_id)

        return Response("Данные для расчета нагрузки успешно отправлены на сервер.")


    def destroy(self, request, pk=None):
        load_template = LoadTemplate.objects.get(pk=pk)
        if load_template.shops.exists():
            raise FieldError(self.error_messages["load_template_attached_shops"])

        load_template.delete()

        return Response(status=204)


    @action(detail=False, methods=['post'])
    @get_uploaded_file
    def upload(self, request, file):
        data = LoadTemplateUploadSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        return upload_load_template(file, data.validated_data, lang=request.user.lang)
    

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        return download_load_template(request, pk)
