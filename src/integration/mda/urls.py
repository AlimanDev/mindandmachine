from django.urls import path

from .views import IntegrationDataExportView

urlpatterns = [
    path('integration_data_export/', IntegrationDataExportView.as_view(), name='mda_integration_data_export'),
]
