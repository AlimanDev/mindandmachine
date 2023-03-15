from django.conf.urls import include
from django.urls import re_path
from dj_rest_auth.views import LoginView, LogoutView, PasswordChangeView
from rest_framework_nested import routers

from src.base.auth.views import (
    WFMTokenLoginView,
    OneTimePassView,
)
from src.base.shop.views import ShopViewSet
from src.base.views import (
    ContentBlockViewSet,
    EmploymentViewSet,
    UserViewSet,
    FunctionGroupView,
    AuthUserView,
    WorkerPositionViewSet,
    ShopSettingsViewSet,
    NetworkViewSet,
    GroupViewSet,
    BreakViewSet,
    ShopScheduleViewSet,
    EmployeeViewSet,
)
from .sawhsettings.views import SAWHSettingsViewSet
from .shift_schedule.views import (
    ShiftScheduleViewSet,
    ShiftScheduleIntervalViewSet,
)

auth_urls = [
    re_path(r'^login/$', LoginView.as_view(), name='rest_login'),
    re_path(r'^logout/$', LogoutView.as_view(), name='rest_logout'),
    re_path(r'^password/change/$', PasswordChangeView.as_view(), name='rest_password_change'),
    re_path(r'^user/$', AuthUserView.as_view(), name='user'),
    re_path(r'^allowed_functions/$', FunctionGroupView.as_view({'get': 'list'}), name='user'),
    re_path(r'^signin_token/?$', WFMTokenLoginView.as_view(), kwargs={'version': '0.9'}, name='signin_token'),
    # Использует Ортека старый формат
    # url(r'^notification', NotificationViewSet.as_view(), name='notification'),
    re_path(r'^otp/$', OneTimePassView.as_view(), name='one_time_pass'),
]

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r'department', ShopViewSet, basename='Shop')
router.register(r'employment', EmploymentViewSet, basename='Employment')
router.register(r'user', UserViewSet, basename='User')
router.register(r'employee', EmployeeViewSet, basename='Employee')
router.register(r'worker_position', WorkerPositionViewSet, basename='WorkerPosition')
router.register(r'shop_settings', ShopSettingsViewSet, basename='ShopSettings')
router.register(r'network', NetworkViewSet, basename='Network')
router.register(r'function_group', FunctionGroupView, basename='FunctionGroupView')
router.register(r'group', GroupViewSet, basename='Group')
router.register(r'break', BreakViewSet, basename='Break')
router.register(r'shift_schedule', ShiftScheduleViewSet, basename='ShiftSchedule')
router.register(r'shift_schedule_interval', ShiftScheduleIntervalViewSet, basename='ShiftScheduleInterval')
router.register(r'content_block', ContentBlockViewSet, basename='ContentBlock')
router.register(r'sawh_settings', SAWHSettingsViewSet, basename='SAWHSettings')

employment_nested_router = routers.NestedSimpleRouter(router, r'employment', lookup='employment')
shop_nested_router = routers.NestedSimpleRouter(router, r'department', lookup='department')
shop_nested_router.register(r'schedule', ShopScheduleViewSet, basename='ShopSchedule')

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    re_path(r'^auth/', include((auth_urls, 'auth'), namespace='auth')),
    re_path(r'^', include(router.urls)),
    re_path(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    re_path(r'^', include(shop_nested_router.urls)),
]
