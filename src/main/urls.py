from django.contrib import admin
from django.urls import path, include
from .cashbox import urls as cashbox_urls
from .timetable import urls as timetable_urls


urlpatterns = [
    path('cashbox/', include(cashbox_urls)),
    path('timetable/', include(timetable_urls)),
    path('admin/', admin.site.urls),
]
