from src.interfaces.api.views.reports import ReportsViewSet
from django.conf.urls import include
from django.urls import re_path
from rest_framework_nested import routers


router = routers.DefaultRouter()
router.register(r'report', ReportsViewSet, basename='Reports')


urlpatterns = [
    re_path(r'^', include(router.urls)),
]
