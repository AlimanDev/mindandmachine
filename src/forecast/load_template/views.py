from rest_framework import serializers, viewsets, status, permissions
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from django_filters import CharFilter
from src.forecast.models import LoadTemplate
from src.forecast.load_template.utils import create_load_template_for_shop, apply_load_template, calculate_shop_load
from rest_framework.decorators import action
from src.conf.djconfig import QOS_DATE_FORMAT
from src.forecast.operation_type_template.views import OperationTypeTemplateSerializer
from src.base.exceptions import MessageError


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
        if shop_id:
            apply_load_template(load_template_id, shop_id, dt_from)
        else:
            load_template = LoadTemplate.objects.get(pk=load_template_id)
            for shop in load_template.shops.all():
                apply_load_template(load_template_id, shop.id, dt_from)
        
        return Response(status=200)


    @action(detail=False, methods=['post'])
    def calculate(self, request):
        data = LoadTemplateSpecSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shop_id = data.validated_data.get('shop_id')
        load_template = LoadTemplate.objects.get(pk=data.validated_data.get('id'))
        dt_from = data.validated_data.get('dt_from')
        dt_to = data.validated_data.get('dt_to')
        if shop_id:
            res = calculate_shop_load(load_template.shops.get(pk=shop_id), load_template, dt_from, dt_to)
        else:
            for shop in load_template.shops.all():
                res = calculate_shop_load(shop, load_template, dt_from, dt_to)
                if not res[1]:
                    break
        status_code = 200 if res[1] else 400

        return Response([res[0]],status=status_code)


    def destroy(self, request, pk=None):
        load_template = LoadTemplate.objects.get(pk=pk)
        if load_template.shops.exists():
            raise MessageError(code="load_template_attached_shops", lang=requset.user.lang)

        load_template.operation_type_templates.all().delete()
        load_template.delete()

        return Response(status=204)
