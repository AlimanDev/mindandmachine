from django.contrib import admin

from .models import ReportConfig


@admin.register(ReportConfig)
class ReportConfigAdmin(admin.ModelAdmin):
    pass
