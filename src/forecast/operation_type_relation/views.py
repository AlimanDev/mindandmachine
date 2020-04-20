from rest_framework import serializers, viewsets, status, permissions
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.forecast.models import OperationTypeTemplate, OperationTypeRelation, OperationType
import re
from src.forecast.operation_type_template.views import OperationTypeTemplateSerializer
from django_filters import NumberFilter
from rest_framework.validators import UniqueTogetherValidator
from src.base.exceptions import MessageError


# Serializers define the API representation.
class OperationTypeRelationSerializer(serializers.ModelSerializer):
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
        super().is_valid(*args, **kwargs)
        lambda_check = r'^(if|else|\+|-|\*|/|\s|a|[0-9]|=|>|<)*'
        if not re.fullmatch(lambda_check, self.validated_data['formula']):
            raise MessageError(code="error_in_formula", lang=self.context['request'].user.lang, params={'formula': self.validated_data['formula']})

        self.validated_data['formula'] = "lambda a: " + self.validated_data['formula']
        if self.validated_data['depended_id'] == self.validated_data['base_id']:
            raise MessageError(code="depended_base_same", lang=self.context['request'].user.lang,)
        
        depended = OperationTypeTemplate.objects.get(pk=self.validated_data['depended_id'])
        base = OperationTypeTemplate.objects.get(pk=self.validated_data['base_id'])
        self.validated_data['depended'] = depended
        self.validated_data['base'] = base

        if base.do_forecast != OperationType.FORECAST_FORMULA:
            raise MessageError(code="base_not_formula", lang=self.context['request'].user.lang,)
        
        if (depended.load_template_id != base.load_template_id):
            raise MessageError(code="not_same_template", lang=self.context['request'].user.lang,)
        
        if OperationTypeRelation.objects.filter(base=depended, depended=base).exists():
            raise MessageError(code="reversed_relation", lang=self.context['request'].user.lang,)

        self.check_relations(base.id, depended.id)

    def check_relations(self, base_id, depended_id):
        relations = list(OperationTypeRelation.objects.filter(base_id=depended_id))
        if not len(relations):
            return True
        else:
            for relation in relations:
                if relation.depended_id == base_id:
                    raise MessageError(code="cycle_relation", lang=self.context['request'].user.lang,)
                else:
                    self.check_relations(self, base_id, relation.depended_id)


class OperationTypeRelationFilter(FilterSet):
    load_teplate = NumberFilter(field_name='base__load_template_id')
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
