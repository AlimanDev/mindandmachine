from django.conf.urls import url, include
from rest_framework import routers
from src.forecast.operation_type_name.views import OperationTypeNameViewSet
from src.forecast.operation_type.views import OperationTypeViewSet


router = routers.DefaultRouter()
router.register(r'operation_type_name', OperationTypeNameViewSet, basename='OperationTypeName')
router.register(r'operation_type', OperationTypeViewSet, basename='OperationType')


urlpatterns = [
    url(r'^', include(router.urls)),
]