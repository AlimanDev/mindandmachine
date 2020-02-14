from django.conf.urls import url, include
from rest_framework import routers
from src.forecast.operation_template.views import OperationTemplateViewSet

router = routers.DefaultRouter()
router.register(r'operation_template', OperationTemplateViewSet, basename='OperationTemplate')


urlpatterns = [
    url(r'^', include(router.urls)),
] 