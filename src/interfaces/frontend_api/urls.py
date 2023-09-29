from rest_framework import routers

from src.interfaces.frontend_api.views.timetable import TimetableViewSet


router = routers.DefaultRouter()
router.register(r'timetable', TimetableViewSet, basename='TimeTable')

urlpatterns = [
    *router.get_urls(),
]
