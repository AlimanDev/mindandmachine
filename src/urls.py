from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from src.util.openapi.auto_schema import WFMOpenAPISchemaGenerator, WFMIntegrationAPISchemaGenerator

from src.base import urls as base_api
from src.conf.djconfig import DEBUG
from src.forecast import urls as forecast_api
from src.main.auth import urls as auth_urls
from src.main.cashbox import urls as cashbox_urls
from src.main.demand import urls as demand_urls
from src.main.download import urls as download_urls
from src.main.operation_template import urls as operation_template_urls
from src.main.other import urls as other_urls
from src.main.shop import urls as shop_urls
from src.main.tablet import urls as tablet_urls
from src.main.timetable import urls as timetable_urls
from src.main.upload import urls as upload_urls
from src.main.urv import urls as urv_urls
from src.misc import urls as misc_api
from src.recognition.urls import router as recognition_router
from src.timetable import urls as timetable_api
from src.timetable.views import RecalcWhAdminView
from src.recognition.views import DownloadViolatorsReportAdminView

api_urlpatterns = [
    path('auth/', include(auth_urls)),
    path('cashbox/', include(cashbox_urls)),
    path('demand/', include(demand_urls)),
    path('download/', include(download_urls)),
    path('other/', include(other_urls)),
    path('operation_template/', include(operation_template_urls)),
    path('shop/', include(shop_urls)),
    path('tablet/', include(tablet_urls)),
    path('timetable/', include(timetable_urls)),
    path('upload/', include(upload_urls)),
    path('urv/', include(urv_urls)),
    path('v1/', include('src.recognition.urls')),  # time attendance api urls
]


urlpatterns = [
    path('api/', include(api_urlpatterns)),
    path('admin/timetable/workerday/recalc_wh/', RecalcWhAdminView.as_view(), name='recalc_wh'),
    path('admin/recognition/ticks/download_violators/', DownloadViolatorsReportAdminView.as_view(), name='download_violators'),
    path('admin/', admin.site.urls),
    path('rest_api/recognition/', include(recognition_router.get_urls())),
    path('rest_api/', include(
        base_api.urlpatterns +
        timetable_api.urlpatterns +
        forecast_api.urlpatterns +
        misc_api.urlpatterns
    )),
]

if settings.QOS_DEV_STATIC_ENABLED:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),

    ] + urlpatterns


from django.views.generic import TemplateView

# urlpatterns += [path('openapi/', get_schema_view(
#     title="WFM",
#     description="Документация REST API",
#     version="1.0.0"
# ), name='openapi-schema'),
# ]
# urlpatterns +=  [
#     # ...
#     # Route TemplateView to serve Swagger UI template.
#     #   * Provide `extra_context` with view name of `SchemaView`.
#     path('swagger-ui/', TemplateView.as_view(
#         template_name='swagger-ui.html',
#         extra_context={'schema_url':'openapi-schema'}
#     ), name='swagger-ui'),
# ]


schema_view = get_schema_view(
   openapi.Info(
      title="WFM",
      default_version='v1',
      description="Документация REST API",
    #   terms_of_service="https://www.google.com/policies/terms/",
    #   contact=openapi.Contact(email="contact@snippets.local"),
    #   license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.IsAdminUser,),
   generator_class=WFMOpenAPISchemaGenerator,
)
integration_schema_view = get_schema_view(
   openapi.Info(
      title="WFM",
      default_version='v1',
      description="Документация REST API для интеграции",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
   generator_class=WFMIntegrationAPISchemaGenerator,
)

urlpatterns += [
   url(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
   url(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
   url(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
   url(r'^redoc_integration/$', integration_schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc-integration'),
]
