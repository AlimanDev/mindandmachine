from django.contrib import admin

from .models import ReportConfig, ReportType


@admin.register(ReportConfig)
class ReportConfigAdmin(admin.ModelAdmin):
    pass

@admin.register(ReportType)
class ReportTypeAdmin(admin.ModelAdmin):
    pass
