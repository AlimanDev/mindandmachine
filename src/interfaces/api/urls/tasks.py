from django.conf.urls import include
from django.urls import re_path
from rest_framework_nested import routers

from src.interfaces.api.views.tasks import TaskViewSet

router = routers.DefaultRouter()
router.register(r'task', TaskViewSet, basename='Task')

urlpatterns = [
    re_path(r'^', include(router.urls)),
]
