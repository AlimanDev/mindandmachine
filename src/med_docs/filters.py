from django_filters.rest_framework import (
    FilterSet,
    NumberFilter,
)

from src.base.filters import (
    BaseActiveNamedModelFilter,
)
from src.util.drf.filters import (
    ListFilter,
)
from .models import (
    MedicalDocumentType,
    MedicalDocument,
)


class MedicalDocumentTypeFilter(BaseActiveNamedModelFilter):
    class Meta:
        model = MedicalDocumentType
        fields = {
            'id': ['exact', 'in'],
            'code': ['exact', 'in'],
        }


class MedicalDocumentFilter(FilterSet):
    employee_id = NumberFilter(field_name='employee_id')
    employee_id__in = ListFilter(field_name='employee_id', lookup_expr='in')
    medical_document_type_id = NumberFilter(field_name='medical_document_type_id')
    medical_document_type_id__in = ListFilter(field_name='medical_document_type_id', lookup_expr='in')

    class Meta:
        model = MedicalDocument
        fields = {
            'dt_from': ['gte', 'lte'],
            'dt_to': ['gte', 'lte'],
        }
