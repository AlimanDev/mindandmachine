from rest_framework import serializers, viewsets, status, permissions
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from src.forecast.models import OperationTypeTemplate, OperationTypeRelation, OperationType
import re
from src.forecast.operation_type_template.views import OperationTypeTemplateSerializer
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


class OperationTypeRelationFilter(FilterSet):

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


    def create(self, request):
        lambda_check = r'^lambda a:(.*)'
        data = OperationTypeRelationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        depended = data.validated_data.get('depended_id')
        base = data.validated_data.get('base_id')
        formula = data.validated_data.get('formula')
        
        if depended == base:
            return Response(['Depended and base are the same'], status=400)

        if not re.fullmatch(lambda_check, formula):
            return Response(['Error in formula'], status=400)

        depended = OperationTypeTemplate.objects.get(pk=depended)
        base = OperationTypeTemplate.objects.get(pk=base)

        if (depended.load_template_id != base.load_template_id):
            return Response(['Base and depended models have not same load template'], status=400)

        if base.do_forecast != OperationType.FORECAST_FORMULA:
            return Response(['Base operation is not formula type'], status=400)

        if OperationTypeRelation.objects.filter(base=base, depended=depended).exists():
            return Response(['Such relation already exists'], status=400)

        if OperationTypeRelation.objects.filter(base=depended, depended=base).exists():
            return Response(['Reversed relation already exists'], status=400)

        relaton = OperationTypeRelation.objects.create(
            base=base,
            depended=depended,
            formula=formula,
        )
        
        return Response(OperationTypeRelationSerializer(relaton).data,status=201)


    def update(self, request, pk=None):
        lambda_check = r'^lambda a:(.*)'
        operation_type_relation = OperationTypeRelation.objects.get(pk=pk)
        data = OperationTypeRelationSerializer(data=request.data, instance=operation_type_relation)
        data.is_valid(raise_exception=True)
        depended = data.validated_data.get('depended_id')
        base = data.validated_data.get('base_id')
        formula = data.validated_data.get('formula')

        if not re.fullmatch(lambda_check, formula):
            return Response(['Error in formula'], status=400)

        depended = OperationTypeTemplate.objects.get(pk=depended)
        base = OperationTypeTemplate.objects.get(pk=base)

        if (depended.load_template_id != base.load_template_id):
            return Response(['Base and depended models have not same load template'], status=400)

        if base.do_forecast != OperationType.FORECAST_FORMULA:
            return Response(['Base operation is not formula type'], status=400)

        if (operation_type_relation.base_id != base.id or operation_type_relation.depended_id != depended.id) and \
             OperationTypeRelation.objects.filter(base=base, depended_id=depended).exists():
            return Response(['Such relation already exists'], status=400)

        if OperationTypeRelation.objects.filter(base_id=depended, depended=base).exists():
            return Response(['Reversed relation already exists'], status=400)

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
