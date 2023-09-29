from src.apps.base.permissions import Permission
from src.apps.base.views_abstract import (
    BaseModelViewSet,
    BaseActiveNamedModelViewSet,
)
from src.apps.med_docs.filters import (
    MedicalDocumentTypeFilter,
    MedicalDocumentFilter,
)
from src.apps.med_docs.models import (
    MedicalDocumentType,
    MedicalDocument,
)
from src.interfaces.api.serializers.med_docs import (
    MedicalDocumentTypeSerializer,
    MedicalDocumentSerializer,
)


class MedicalDocumentTypeViewSet(BaseActiveNamedModelViewSet):
    serializer_class = MedicalDocumentTypeSerializer
    permission_classes = [Permission]
    openapi_tags = ['MedicalDocumentType', ]
    filterset_class = MedicalDocumentTypeFilter
    queryset = MedicalDocumentType.objects


class MedicalDocumentViewSet(BaseModelViewSet):
    serializer_class = MedicalDocumentSerializer
    permission_classes = [Permission]
    openapi_tags = ['MedicalDocument', ]
    filterset_class = MedicalDocumentFilter
    queryset = MedicalDocument.objects
