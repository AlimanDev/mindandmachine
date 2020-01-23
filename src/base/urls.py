from django.conf.urls import url, include
from rest_framework import routers
from src.base.shop.views import ShopViewSet
from src.base.views import EmploymentViewSet, UserViewSet

from rest_auth.views import (
    LoginView, LogoutView, PasswordChangeView
)

rest_auth_urls = [
    url(r'^login/$', LoginView.as_view(), name='rest_login'),
    url(r'^logout/$', LogoutView.as_view(), name='rest_logout'),
    url(r'^password/change/$', PasswordChangeView.as_view(),
        name='rest_password_change'),
]

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'department', ShopViewSet, basename='Shop')
router.register(r'employment', EmploymentViewSet, basename='Employment')
router.register(r'user', UserViewSet, basename='User')

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^auth/', include(rest_auth_urls))
]
