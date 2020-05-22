import re

from django_filters import NumberFilter
from django_filters.rest_framework import FilterSet
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers, viewsets, status, permissions
from rest_framework.validators import UniqueTogetherValidator
from rest_framework.response import Response

from src.forecast.models import OperationTypeTemplate, OperationTypeRelation, OperationType
from src.forecast.operation_type_template.views import OperationTypeTemplateSerializer
from src.forecast.load_template.utils import create_operation_type_relations_dict
from src.base.exceptions import FieldError

# Serializers define the API representation.
class OperationTypeRelationSerializer(serializers.ModelSerializer):
    default_error_messages = {
        "depended_base_same": _("Base and depended demand models cannot be the same."),
        "cycle_relation": _("Demand model cannot depend on itself."),
        "reversed_relation": _("Backward dependency already exists."),
        "not_same_template": _("Base and depended demand models cannot have different templates."),
        "error_in_formula": _("Error in formula: {formula}."),
        "base_not_formula": _("Base model."),
    }

    formula = serializers.CharField()
    depended = OperationTypeTemplateSerializer(read_only=True)
    base = OperationTypeTemplateSerializer(read_only=True)
    depended_id = serializers.IntegerField(write_only=True)
    base_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = OperationTypeRelation
        fields = ['id', 'base', 'depended', 'formula', 'depended_id', 'base_id']
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
        if not re.fullmatch(lambda_check, self.validated_data['formula']):
            raise FieldError(self.error_messages["base_not_formula"].format(formula=self.validated_data['formula']), 'formula')

        self.validated_data['formula'] = "lambda a: " + self.validated_data['formula']
        if self.validated_data['depended_id'] == self.validated_data['base_id']:
            raise FieldError(self.error_messages["depended_base_same"])

        depended = OperationTypeTemplate.objects.get(pk=self.validated_data['depended_id'])
        base = OperationTypeTemplate.objects.get(pk=self.validated_data['base_id'])
        self.validated_data['depended'] = depended
        self.validated_data['base'] = base

        if base.do_forecast != OperationType.FORECAST_FORMULA:
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


class OperationTypeRelationFilter(FilterSet):
    load_template = NumberFilter(field_name='base__load_template_id')
    class Meta:
        model = OperationTypeRelation
        fields = {
            'base_id': ['exact',],
            'depended_id': ['exact',],
        }


class OperationTypeRelationViewSet(viewsets.ModelViewSet):
    """

   
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = OperationTypeRelationSerializer
    filterset_class = OperationTypeRelationFilter

    def get_queryset(self):
        return self.filter_queryset(OperationTypeRelation.objects.all())


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
