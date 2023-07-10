from django.conf.urls import include
from django.urls import re_path
from rest_framework import routers
from src.interfaces.api.views.operation_type_name import OperationTypeNameViewSet
from src.interfaces.api.views.operation_type import OperationTypeViewSet
from src.interfaces.api.views.period_clients import PeriodClientsViewSet
from src.interfaces.api.views.operation_type_template import OperationTypeTemplateViewSet
from src.interfaces.api.views.operation_type_relation import OperationTypeRelationViewSet
from src.interfaces.api.views.load_template import LoadTemplateViewSet
from src.interfaces.api.views.receipt import ReceiptViewSet

router = routers.DefaultRouter()
router.register(r'operation_type_name', OperationTypeNameViewSet, basename='OperationTypeName')
router.register(r'operation_type', OperationTypeViewSet, basename='OperationType')
#Depricated
router.register(r'period_clients', PeriodClientsViewSet, basename='PeriodClients')
router.register(r'timeserie_value', PeriodClientsViewSet, basename='PeriodClients')
router.register(r'operation_type_template', OperationTypeTemplateViewSet, basename='OperationTypeTemplate')
router.register(r'operation_type_relation', OperationTypeRelationViewSet, basename='OperationTypeRelation')
router.register(r'load_template', LoadTemplateViewSet, 'LoadTemplate')
router.register(r'receipt', ReceiptViewSet, 'Receipt')


urlpatterns = [
    re_path(r'^', include(router.urls)),
]
