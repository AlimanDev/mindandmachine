from rest_framework import serializers, status
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.forecast.models import OperationTypeTemplate, LoadTemplate
from src.forecast.operation_type_name.views import OperationTypeNameSerializer
from rest_framework.validators import UniqueTogetherValidator
from src.base.permissions import Permission
from src.base.views_abstract import BaseModelViewSet
from drf_yasg.utils import swagger_auto_schema

# Serializers define the API representation.
class OperationTypeTemplateSerializer(serializers.ModelSerializer):
    operation_type_name = OperationTypeNameSerializer(read_only=True)
    operation_type_name_id = serializers.IntegerField(write_only=True)
    load_template_id = serializers.IntegerField()

    class Meta:
        model = OperationTypeTemplate
        fields = ['id', 'load_template_id', 'operation_type_name_id', 'operation_type_name', 'tm_from', 'tm_to', 'forecast_step']
        validators = [
            UniqueTogetherValidator(
                queryset=OperationTypeTemplate.objects.all(),
                fields=['load_template_id', 'operation_type_name_id'],
            ),
        ]


class OperationTypeTemplateFilter(FilterSet):

    class Meta:
        model = OperationTypeTemplate
        fields = {
            'load_template_id': ['exact', ]
        }


class OperationTypeTemplateViewSet(BaseModelViewSet):
    """
    Шаблон типа операции в LoadTemplate   
    """
    permission_classes = [Permission]
    filterset_class = OperationTypeTemplateFilter
    serializer_class = OperationTypeTemplateSerializer

    def get_queryset(self):
        return OperationTypeTemplate.objects.filter(
            load_template__network_id=self.request.user.network_id
        )

    @swagger_auto_schema(
        operation_description='''
        После создания новых шаблонов или обновления существующих
        необходимо будет отправить запрос в LoadTemplate, чтобы применить
        эти изменения для магазинов.
        '''
    )
    def update(self, request, pk=None):
        data = OperationTypeTemplateSerializer(data=request.data, instance=OperationTypeTemplate.objects.get(pk=pk))
        data.is_valid(raise_exception=True)
        data.validated_data.pop('load_template_id', None)
        data.save()

        return Response(data.data, status=200)
