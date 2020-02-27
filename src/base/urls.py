from django.conf.urls import url, include
from rest_framework import routers, urls
from src.base.shop.views import ShopViewSet
from src.base.views import EmploymentViewSet, UserViewSet, FunctionGroupView, AuthUserView
from src.base.worker_position.views import WorkerPositionViewSet
from rest_auth.views import (
    LoginView, LogoutView, PasswordChangeView
)

rest_auth_urls = [
    url(r'^login/$', LoginView.as_view(), name='rest_login'),
    url(r'^logout/$', LogoutView.as_view(), name='rest_logout'),
    url(r'^password/change/$', PasswordChangeView.as_view(), name='rest_password_change'),
    url(r'^user/$', AuthUserView.as_view(), name='user'),
    url(r'^allowed_functions/$', FunctionGroupView.as_view(), name='user'),
]

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'department', ShopViewSet, basename='Shop')
router.register(r'employment', EmploymentViewSet, basename='Employment')
router.register(r'user', UserViewSet, basename='User')
router.register(r'worker_position', WorkerPositionViewSet, basename='WorkerPosition')


# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    url(r'^auth/', include((rest_auth_urls,'auth'),namespace='auth')),
    url(r'^', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]
