from django_filters import NumberFilter, OrderingFilter, CharFilter, DurationFilter
from django_filters.rest_framework import FilterSet

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from rest_framework.pagination import LimitOffsetPagination
from src.interfaces.api.serializers.base import BaseModelSerializer

from src.apps.forecast.models import OperationTypeRelation
from src.interfaces.api.views.operation_type_template import OperationTypeTemplateSerializer
from src.apps.base.permissions import Permission
from src.apps.base.views_abstract import BaseModelViewSet

# Serializers define the API representation.
class OperationTypeRelationSerializer(BaseModelSerializer):
    formula = serializers.CharField(required=False)
    depended = OperationTypeTemplateSerializer(read_only=True)
    base = OperationTypeTemplateSerializer(read_only=True)
    depended_id = serializers.IntegerField(write_only=True)
    base_id = serializers.IntegerField(write_only=True)
    type = serializers.CharField(read_only=True)
    days_of_week = serializers.ListField(required=False, allow_null=True, allow_empty=True, child=serializers.IntegerField(), write_only=True)

    class Meta:
        model = OperationTypeRelation
        fields = ['id', 'base', 'depended', 'formula', 'depended_id', 'base_id', 'type', 'max_value', 'threshold', 'days_of_week', 'order']
        validators = [
            UniqueTogetherValidator(
                queryset=OperationTypeRelation.objects.all(),
                fields=['base_id', 'depended_id'],
            ),
        ]

    def to_representation(self, instance: OperationTypeRelation):
        data = super().to_representation(instance)
        data['days_of_week'] = instance.days_of_week_list
        return data


class OperationTypeRelationFilter(FilterSet):
    load_template = NumberFilter(field_name='base__load_template_id')
    base_name_id = NumberFilter(field_name='base__operation_type_name_id')
    base_name = CharFilter(field_name='base__operation_type_name__name', lookup_expr='icontains')
    depended_name_id = NumberFilter(field_name='depended__operation_type_name_id')
    depended_name = CharFilter(field_name='depended__operation_type_name__name', lookup_expr='icontains')
    forecast_step = DurationFilter(field_name='base__forecast_step')
    formula = CharFilter(field_name='formula', lookup_expr='icontains')
    ordering = OrderingFilter(
        fields=(
            'base__operation_type_name__name', 
            'depended__operation_type_name__name', 
            'base__forecast_step',
        ),
    )
    class Meta:
        model = OperationTypeRelation
        fields = {
            'base_id': ['exact',],
            'depended_id': ['exact',],
        }


class OperationTypeRelationViewSet(BaseModelViewSet):
    """
    Отношения типов операций через формулу или через прогноз   
    """
    permission_classes = [Permission]
    serializer_class = OperationTypeRelationSerializer
    filterset_class = OperationTypeRelationFilter
    openapi_tags = ['OperationTypeRelation',]
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        return OperationTypeRelation.objects.filter(
            base__load_template__network_id=self.request.user.network_id,
        ).select_related('depended', 'base')
