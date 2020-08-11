from django.conf.urls import url, include
from rest_framework import routers
from src.forecast.operation_type_name.views import OperationTypeNameViewSet
from src.forecast.operation_type.views import OperationTypeViewSet
from src.forecast.period_clients.views import PeriodClientsViewSet
from src.forecast.operation_template.views import OperationTemplateViewSet
from src.forecast.operation_type_template.views import OperationTypeTemplateViewSet
from src.forecast.operation_type_relation.views import OperationTypeRelationViewSet
from src.forecast.load_template.views import LoadTemplateViewSet

router = routers.DefaultRouter()
router.register(r'operation_type_name', OperationTypeNameViewSet, basename='OperationTypeName')
router.register(r'operation_type', OperationTypeViewSet, basename='OperationType')
#Depricated
router.register(r'period_clients', PeriodClientsViewSet, basename='PeriodClients')
router.register(r'timeserie_value', PeriodClientsViewSet, basename='PeriodClients')
router.register(r'operation_template', OperationTemplateViewSet, basename='OperationTemplate')
router.register(r'operation_type_template', OperationTypeTemplateViewSet, basename='OperationTypeTemplate')
router.register(r'operation_type_relation', OperationTypeRelationViewSet, basename='OperationTypeRelation')
router.register(r'load_template', LoadTemplateViewSet, 'LoadTemplate')


urlpatterns = [
    url(r'^', include(router.urls)),
]
