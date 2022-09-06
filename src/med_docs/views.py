from src.base.permissions import Permission
from src.base.views_abstract import (
    BaseModelViewSet,
    BaseActiveNamedModelViewSet,
)
from .filters import (
    MedicalDocumentTypeFilter,
    MedicalDocumentFilter,
)
from .models import (
    MedicalDocumentType,
    MedicalDocument,
)
from .serializers import (
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
