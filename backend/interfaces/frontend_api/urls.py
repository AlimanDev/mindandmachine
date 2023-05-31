from django.urls import re_path, include

from backend.interfaces.frontend_api.routers import router

urlpatterns = [
    re_path(r'^', include(router.urls)),
]