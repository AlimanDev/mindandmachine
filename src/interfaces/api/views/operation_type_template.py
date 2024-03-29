from rest_framework import serializers
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.interfaces.api.serializers.base import BaseModelSerializer
from src.apps.forecast.models import OperationTypeTemplate
from src.interfaces.api.views.operation_type_name import OperationTypeNameSerializer
from rest_framework.validators import UniqueTogetherValidator
from src.apps.base.permissions import Permission
from src.apps.base.exceptions import FieldError

from django.utils.translation import gettext_lazy as _

from datetime import timedelta
from src.apps.base.views_abstract import BaseModelViewSet
from drf_yasg.utils import swagger_auto_schema

# Serializers define the API representation.
class OperationTypeTemplateSerializer(BaseModelSerializer):
    default_error_messages = {
        "bad_steps_base": _("This operation type depends on operations with less forecast steps."),
        "bad_steps_depended": _("This operation type is dependency of operations with bigger forecast steps."),
        "cant_set_constant": _("You cant set constant value because this operation has depndences."),
    }

    operation_type_name = OperationTypeNameSerializer(read_only=True)
    operation_type_name_id = serializers.IntegerField(write_only=True)
    load_template_id = serializers.IntegerField()

    class Meta:
        model = OperationTypeTemplate
        fields = ['id', 'load_template_id', 'operation_type_name_id', 'operation_type_name', 'tm_from', 'tm_to', 'forecast_step', 'const_value']
        validators = [
            UniqueTogetherValidator(
                queryset=OperationTypeTemplate.objects.all(),
                fields=['load_template_id', 'operation_type_name_id'],
            ),
        ]

    def update(self, instance, validated_data):
        const_value = validated_data.get('const_value')
        if const_value and instance.depends.exists():
            raise FieldError(self.error_messages["cant_set_constant"])
        new_timestep = validated_data.get('forecast_step')
        impossible_dependences = []
        impossible_bases = []
        if new_timestep == timedelta(days=1):
            impossible_dependences = [timedelta(hours=1), timedelta(minutes=30),]
        elif new_timestep == timedelta(hours=1):
            impossible_dependences = [timedelta(minutes=30),]
            impossible_bases = [timedelta(days=1),]
        elif new_timestep == timedelta(minutes=30):
            impossible_bases = [timedelta(days=1),timedelta(hours=1)]

        dependences = instance.depends.filter(depended__forecast_step__in=impossible_dependences).exists()
        if dependences:
            raise FieldError(self.error_messages["bad_steps_base"])
        bases = instance.bases.filter(base__forecast_step__in=impossible_bases).exists()
        if bases:
            raise FieldError(self.error_messages["bad_steps_depended"])
        return super().update(instance, validated_data)


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
    openapi_tags = ['OperationTypeTemplate',]

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
