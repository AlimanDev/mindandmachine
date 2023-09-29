from django.contrib import admin

from src.apps.base.admin_filters import CustomChoiceDropdownFilter, RelatedOnlyDropdownLastNameOrderedFilter, RelatedOnlyDropdownNameOrderedFilter
from .models import (
    Report,
    ReportPermission,
)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        'name',
    )
    save_as = True


@admin.register(ReportPermission)
class ReportPermissionAdmin(admin.ModelAdmin):
    list_display = (
        'group',
        'user',
        'report',
    )
    list_filter = (
        ('group', RelatedOnlyDropdownNameOrderedFilter),
        ('user', RelatedOnlyDropdownLastNameOrderedFilter),
        ('report', RelatedOnlyDropdownNameOrderedFilter),
    )
    raw_id_fields = (
        'group',
        'user',
        'report',
    )
    save_as = True
