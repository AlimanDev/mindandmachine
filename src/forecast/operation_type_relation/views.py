import re

from datetime import timedelta

from django_filters import NumberFilter, OrderingFilter, CharFilter, DurationFilter
from django_filters.rest_framework import FilterSet
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers, status
from rest_framework.validators import UniqueTogetherValidator
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination

from src.forecast.models import OperationTypeTemplate, OperationTypeRelation, OperationType, OperationTypeName
from src.forecast.operation_type_template.views import OperationTypeTemplateSerializer
from src.forecast.load_template.utils import create_operation_type_relations_dict
from src.base.exceptions import FieldError
from src.base.permissions import Permission
from src.base.views_abstract import BaseModelViewSet

# Serializers define the API representation.
class OperationTypeRelationSerializer(serializers.ModelSerializer):
    default_error_messages = {
        "depended_base_same": _("Base and depended demand models cannot be the same."),
        "cycle_relation": _("Demand model cannot depend on itself."),
        "reversed_relation": _("Backward dependency already exists."),
        "not_same_template": _("Base and depended demand models cannot have different templates."),
        "error_in_formula": _("Error in formula: {formula}."),
        "base_not_formula": _("Base model not formula."),
        "const_cant_be_base": _("Constant operation can\'t be base."),
        "bad_steps":_("Depended must have same or bigger forecast step, got {} -> {}"),
        "bad_day_of_week": _("Bad day of week, possible values: 0, 1, 2, 3, 4, 5, 6")
    }

    formula = serializers.CharField(required=False)
    depended = OperationTypeTemplateSerializer(read_only=True)
    base = OperationTypeTemplateSerializer(read_only=True)
    depended_id = serializers.IntegerField(write_only=True)
    base_id = serializers.IntegerField(write_only=True)
    days_of_week = serializers.ListField(required=False, allow_null=True, allow_empty=True, child=serializers.IntegerField(), write_only=True)

    class Meta:
        model = OperationTypeRelation
        fields = ['id', 'base', 'depended', 'formula', 'depended_id', 'base_id', 'type', 'max_value', 'threshold', 'days_of_week']
        validators = [
            UniqueTogetherValidator(
                queryset=OperationTypeRelation.objects.all(),
                fields=['base_id', 'depended_id'],
            ),
        ]


    def is_valid(self, *args, **kwargs):
        
        if not super().is_valid(*args, **kwargs):
            return False
        lambda_check = r'^(if|else|\+|-|\*|/|\s|a|[0-9]|=|>|<|\.)*'
        if self.validated_data.get('type', 'F') == OperationTypeRelation.TYPE_PREDICTION:
            self.validated_data['formula'] = 'a'
        if self.validated_data.get('type', 'F') == OperationTypeRelation.TYPE_FORMULA and not re.fullmatch(lambda_check, self.validated_data.get('formula', '')):
            raise FieldError(self.error_messages["error_in_formula"].format(formula=self.validated_data['formula']), 'formula')

        if self.validated_data.get('type', 'F') == OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN:
            self.validated_data['formula'] = None
            if not self.validated_data.get('max_value'):
                raise FieldError(self.error_messages['required'], 'max_value')
            if not self.validated_data.get('threshold'):
                raise FieldError(self.error_messages['required'], 'threshold')
            if not self.validated_data.get('days_of_week'):
                raise FieldError(self.error_messages['required'], 'days_of_week')

            days_of_week = self.validated_data.get('days_of_week', [])
            if any([7 in days_of_week, 8 in days_of_week, 9 in days_of_week]):
                raise FieldError(self.error_messages['bad_day_of_week'], 'days_of_week')
            self.validated_data['days_of_week'] = list(set(days_of_week))

        if self.validated_data['depended_id'] == self.validated_data['base_id']:
            raise FieldError(self.error_messages["depended_base_same"])

        depended = OperationTypeTemplate.objects.get(pk=self.validated_data['depended_id'])
        base = OperationTypeTemplate.objects.select_related('operation_type_name').get(pk=self.validated_data['base_id'])
        self.validated_data['depended'] = depended
        self.validated_data['base'] = base

        if (depended.forecast_step == timedelta(hours=1) and not (base.forecast_step in [timedelta(hours=1), timedelta(minutes=30)])) or\
           (depended.forecast_step == timedelta(minutes=30) and not (base.forecast_step in [timedelta(minutes=30)])):
            raise FieldError(self.error_messages["bad_steps"].format(depended.forecast_step, base.forecast_step))

        if not (base.const_value is None):
            raise FieldError(self.error_messages["const_cant_be_base"], 'base')

        if base.operation_type_name.do_forecast != OperationTypeName.FORECAST_FORMULA:
            raise FieldError(self.error_messages["base_not_formula"], 'base')

        if (depended.load_template_id != base.load_template_id):
            raise FieldError(self.error_messages["not_same_template"])

        if OperationTypeRelation.objects.filter(base=depended, depended=base).exists():
            raise FieldError(self.error_messages["reversed_relation"], 'base')

        self.relations = create_operation_type_relations_dict(base.load_template_id)

        self.check_relations(base.id, depended.id)

    def check_relations(self, base_id, depended_id):
        '''
        Функция проверяет отсутсвие цикличных связей
        '''
        relations = self.relations.get(depended_id)
        if not relations:
            return
        else:
            for relation in relations:
                if relation['depended'].id == base_id:
                    raise FieldError(self.error_messages["cycle_relation"],'base')
                else:
                    self.check_relations(base_id, relation['depended'].id)

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


    def update(self, request, pk=None):
        operation_type_relation = OperationTypeRelation.objects.get(pk=pk)
        data = OperationTypeRelationSerializer(data=request.data, instance=operation_type_relation, context={'request': request})
        data.is_valid(raise_exception=True)
        base = data.validated_data.pop('base')
        formula = data.validated_data.get('formula')

        if operation_type_relation.formula != formula:
            OperationType.objects.filter(
                shop__load_template_id=base.load_template_id, 
                operation_type_name_id__in=[
                    base.operation_type_name_id, 
                    operation_type_relation.base.operation_type_name_id
                ],
            ).update(status=OperationType.UPDATED)

        data.save()
        
        return Response(data.data, status=200)


    def destroy(self, request, pk=None):
        operation_type_relation = OperationTypeRelation.objects.get(pk=pk)
        OperationType.objects.filter(
                shop__load_template_id=operation_type_relation.base.load_template_id, 
                operation_type_name_id=operation_type_relation.base.operation_type_name_id,
        ).update(status=OperationType.UPDATED)
        operation_type_relation.delete()
        return Response(status=204)
