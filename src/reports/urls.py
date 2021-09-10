from src.reports.views import ReportsViewSet
from django.conf.urls import url, include
from rest_framework_nested import routers


router = routers.DefaultRouter()
router.register(r'report', ReportsViewSet, basename='Reports')


urlpatterns = [
    url(r'^', include(router.urls)),
]
