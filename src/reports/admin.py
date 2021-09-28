from django.contrib import admin

from .models import ReportConfig, ReportType, Period


@admin.register(ReportConfig)
class ReportConfigAdmin(admin.ModelAdmin):
    pass

@admin.register(ReportType)
class ReportTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    pass
