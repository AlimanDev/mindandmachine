from django.conf.urls import url, include

from rest_framework import routers
from rest_auth.views import (
    LoginView, LogoutView, PasswordChangeView
)
from src.base.shop.views import ShopViewSet
from src.base.views import(
    EmploymentViewSet,
    UserViewSet,
    FunctionGroupView,
    AuthUserView,
    WorkerPositionViewSet,
    NotificationViewSet,
    SubscribeViewSet,
    ShopSettingsViewSet,
    NetworkViewSet)


rest_auth_urls = [
    url(r'^login/$', LoginView.as_view(), name='rest_login'),
    url(r'^logout/$', LogoutView.as_view(), name='rest_logout'),
    url(r'^password/change/$', PasswordChangeView.as_view(), name='rest_password_change'),
    url(r'^user/$', AuthUserView.as_view(), name='user'),
    url(r'^allowed_functions/$', FunctionGroupView.as_view({'get': 'list'}), name='FunctionGroup'),
    # url(r'^notification', NotificationViewSet.as_view(), name='notification')
]

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'department', ShopViewSet, basename='Shop')
router.register(r'employment', EmploymentViewSet, basename='Employment')
router.register(r'user', UserViewSet, basename='User')
router.register(r'worker_position', WorkerPositionViewSet, basename='WorkerPosition')
router.register(r'subscribe', SubscribeViewSet, basename='Subscribe')
router.register(r'notification', NotificationViewSet, basename='Notification')
router.register(r'shop_settings', ShopSettingsViewSet, basename='ShopSettings')
router.register(r'network', NetworkViewSet, basename='Network')
router.register(r'function_group', FunctionGroupView, basename='FunctionGroup')



# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    url(r'^auth/', include((rest_auth_urls,'auth'),namespace='auth')),
    url(r'^', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]
