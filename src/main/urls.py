from django.contrib import admin
from django.urls import path, include
from .timetable import urls as timetable_urls


urlpatterns = [
    path('timetable/', include(timetable_urls)),
    path('admin/', admin.site.urls),
]
