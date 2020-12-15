from rest_framework import serializers, viewsets, status
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.forecast.models import OperationTypeTemplate, LoadTemplate
from src.forecast.operation_type_name.views import OperationTypeNameSerializer
from rest_framework.validators import UniqueTogetherValidator
from src.base.permissions import Permission
from src.base.exceptions import FieldError

from django.utils.translation import gettext_lazy as _

from datetime import timedelta

# Serializers define the API representation.
class OperationTypeTemplateSerializer(serializers.ModelSerializer):
    default_error_messages = {
        "bad_steps_base": _("This operation type depends on operations with less forecast steps."),
        "bad_steps_depended": _("This operation type is dependency of operations with bigger forecast steps."),
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


class OperationTypeTemplateViewSet(viewsets.ModelViewSet):
    """
    После создания новых шаблонов или обновления существующих
    необходимо будет отправить запрос в LoadTemplate, чтобы применить
    эти изменения для магазинов.
   
    """
    permission_classes = [Permission]
    filterset_class = OperationTypeTemplateFilter
    serializer_class = OperationTypeTemplateSerializer

    def get_queryset(self):
        return OperationTypeTemplate.objects.filter(
            load_template__network_id=self.request.user.network_id
        )

    def update(self, request, pk=None):
        data = OperationTypeTemplateSerializer(data=request.data, instance=OperationTypeTemplate.objects.get(pk=pk))
        data.is_valid(raise_exception=True)
        data.validated_data.pop('load_template_id', None)
        data.save()

        return Response(data.data, status=200)
