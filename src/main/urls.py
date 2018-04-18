from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from .cashbox import urls as cashbox_urls
from .timetable import urls as timetable_urls
from .auth import urls as auth_urls
from .demand import urls as demand_urls
from .queue import urls as queue_urls
from .other import urls as other_urls


urlpatterns = [
    path('auth/', include(auth_urls)),
    path('cashbox/', include(cashbox_urls)),
    path('timetable/', include(timetable_urls)),
    path('demand/', include(demand_urls)),
    path('queue/', include(queue_urls)),
    path('other/', include(other_urls)),
    path('admin/', admin.site.urls),
]

if settings.QOS_DEV_STATIC_ENABLED:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
