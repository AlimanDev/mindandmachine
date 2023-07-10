from django.conf.urls import include
from django.urls import re_path
from rest_framework_nested import routers

from src.interfaces.api.views.med_docs import (
    MedicalDocumentTypeViewSet,
    MedicalDocumentViewSet,
)

router = routers.DefaultRouter()
router.register(r'medical_document_type', MedicalDocumentTypeViewSet, basename='MedicalDocumentType')
router.register(r'medical_document', MedicalDocumentViewSet, basename='MedicalDocument')


urlpatterns = [
    re_path(r'^', include(router.urls)),
]
