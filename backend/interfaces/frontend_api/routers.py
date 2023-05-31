from rest_framework import routers

from backend.interfaces.frontend_api.views.shops import ShopViewSet

router = routers.DefaultRouter()
router.register(r'department', ShopViewSet, basename='Shop')
