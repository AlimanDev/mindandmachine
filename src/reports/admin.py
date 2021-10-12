from django.contrib import admin

from src.base.admin import BaseNotWrapRelatedModelaAdmin
from src.reports.forms import ReportConfigForm

from .models import ReportConfig, ReportType, Period


@admin.register(ReportConfig)
class ReportConfigAdmin(BaseNotWrapRelatedModelaAdmin):
    form = ReportConfigForm
    not_wrap_fields = ['report_type', 'cron', 'period']

@admin.register(ReportType)
class ReportTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    pass
