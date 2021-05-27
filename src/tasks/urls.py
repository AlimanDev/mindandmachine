from django.conf.urls import url, include
from rest_framework_nested import routers

from .views import TaskViewSet

router = routers.DefaultRouter()
router.register(r'task', TaskViewSet, basename='Task')

urlpatterns = [
    url(r'^', include(router.urls)),
]
