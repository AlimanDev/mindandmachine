from django.conf.urls import url, include
from rest_framework import routers
from src.forecast.operation_type_name.views import OperationTypeNameViewSet
from src.forecast.operation_type.views import OperationTypeViewSet
from src.forecast.period_clients.views import PeriodClientsViewSet
from src.forecast.operation_template.views import OperationTemplateViewSet


router = routers.DefaultRouter()
router.register(r'operation_type_name', OperationTypeNameViewSet, basename='OperationTypeName')
router.register(r'operation_type', OperationTypeViewSet, basename='OperationType')
router.register(r'period_clients', PeriodClientsViewSet, basename='PeriodClients')
router.register(r'operation_template', OperationTemplateViewSet, basename='OperationTemplate')


urlpatterns = [
    url(r'^', include(router.urls)),
]
