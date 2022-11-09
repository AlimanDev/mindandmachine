from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from src.base import urls as base_api
from src.conf.djconfig import DEBUG
from src.forecast import urls as forecast_api
from src.forecast.views import RecalcLoadAdminView, UploadDemandAdminView
from src.med_docs import urls as med_docs_urls
from src.misc import urls as misc_api
from src.recognition.urls import router as recognition_router
from src.recognition.views import DownloadViolatorsReportAdminView
from src.reports import urls as reports_urls
from src.tasks import urls as task_urls
from src.timetable import urls as timetable_api
from src.timetable.views import RecalcTimesheetAdminView, RecalcWhAdminView
from src.util.openapi.auto_schema import WFMOpenAPISchemaGenerator, WFMIntegrationAPISchemaGenerator

api_urlpatterns = [
    path('v1/', include('src.recognition.urls')),  # time attendance api urls
]


urlpatterns = [
    path('api/', include(api_urlpatterns)),
    path('admin/timetable/workerday/recalc_wh/', RecalcWhAdminView.as_view(), name='recalc_wh'),
    path('admin/timetable/workerday/recalc_timesheet/', RecalcTimesheetAdminView.as_view(), name='recalc_timesheet'),
    path('admin/forecast/loadtemplate/recalc_load/', RecalcLoadAdminView.as_view(), name='recalc_load'),
    path('admin/forecast/periodclients/upload_demand/', UploadDemandAdminView.as_view(), name='upload_demand'),
    path('admin/recognition/ticks/download_violators/', DownloadViolatorsReportAdminView.as_view(), name='download_violators'),
    path('admin/', admin.site.urls),
    path('rest_api/recognition/', include(recognition_router.get_urls())),
    path('rest_api/pbi/', include('src.pbi.urls')),
    path('rest_api/integration/mda/', include('src.integration.mda.urls')),
    path('rest_api/', include(
        base_api.urlpatterns +
        timetable_api.urlpatterns +
        forecast_api.urlpatterns +
        misc_api.urlpatterns +
        task_urls.urlpatterns +
        reports_urls.urlpatterns +
        med_docs_urls.urlpatterns,
    )),
]

if DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),

    ] + urlpatterns

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
   re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
   re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
   re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
   re_path(r'^rest_api/integration_docs/$', integration_schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc-integration'),
]
