from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.urls import path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from src.interfaces.api.urls import base as base_api, med_docs as med_docs_urls, reports as reports_urls, \
    tasks as task_urls, timetable as timetable_api, forecast as forecast_api
from src.conf.djconfig import DEBUG
from src.interfaces.api.views.forecast import RecalcLoadAdminView, UploadDemandAdminView
from src.adapters.metabase import urls as metabase_api
from src.interfaces.api.urls.recognition import router as recognition_router
from src.interfaces.api.views.recognition import DownloadViolatorsReportAdminView
from src.interfaces.api.views.timetable import RecalcTimesheetAdminView, RecalcWhAdminView
from src.common.openapi.auto_schema import WFMOpenAPISchemaGenerator, WFMIntegrationAPISchemaGenerator

from src.interfaces.frontend_api import urls as frontend_api_urls


api_urlpatterns = [
    path('v1/', include('src.interfaces.api.urls.recognition')),  # time attendance tevian urls
]


urlpatterns = [
    path('tevian/', include(api_urlpatterns)),
    path('admin/timetable/workerday/recalc_wh/', RecalcWhAdminView.as_view(), name='recalc_wh'),
    path('admin/timetable/workerday/recalc_timesheet/', RecalcTimesheetAdminView.as_view(), name='recalc_timesheet'),
    path('admin/forecast/loadtemplate/recalc_load/', RecalcLoadAdminView.as_view(), name='recalc_load'),
    path('admin/forecast/periodclients/upload_demand/', UploadDemandAdminView.as_view(), name='upload_demand'),
    path('admin/recognition/ticks/download_violators/', DownloadViolatorsReportAdminView.as_view(), name='download_violators'),
    path('admin/', admin.site.urls),
    path('rest_api/recognition/', include(recognition_router.get_urls())),
    path('rest_api/pbi/', include('src.adapters.pbi.urls')),
    path('rest_api/integration/mda/', include('src.interfaces.api.urls.mda')),
    path('rest_api/', include(
        base_api.urlpatterns +
        forecast_api.urlpatterns +
        metabase_api.urlpatterns +
        task_urls.urlpatterns +
        reports_urls.urlpatterns +
        timetable_api.urlpatterns +
        med_docs_urls.urlpatterns
    )),
    path('rest_api/v2/', include(
        frontend_api_urls.urlpatterns
    ))
]

if DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),

    ] + urlpatterns

schema_view = get_schema_view(
   openapi.Info(
      title="WFM",
      default_version='v1',
      description="Документация REST API",
   ),
   public=True,
   permission_classes=[permissions.IsAdminUser,],
   generator_class=WFMOpenAPISchemaGenerator,
   url=settings.EXTERNAL_HOST,
)
integration_schema_view = get_schema_view(
   openapi.Info(
      title="WFM",
      default_version='v1',
      description="Документация REST API для интеграции",
   ),
   public=True,
   permission_classes=[permissions.AllowAny,],
   generator_class=WFMIntegrationAPISchemaGenerator,
)

urlpatterns += [
   re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
   re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
   re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
   re_path(r'^rest_api/integration_docs/$', integration_schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc-integration'),
]
