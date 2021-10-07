from django.contrib import admin
from src.base.admin_filters import CustomRelatedOnlyDropdownFilter

from src.integration.models import (
    ExternalSystem,
    ShopExternalCode,
    UserExternalCode,
    GenericExternalCode,
)


@admin.register(ExternalSystem)
class ExternalSystemAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')


@admin.register(ShopExternalCode)
class ShopExternalCodeAdmin(admin.ModelAdmin):
    list_display = ('shop', 'attendance_area')
    list_select_related = ('shop', 'attendance_area')
    raw_id_fields = ('shop',)


@admin.register(UserExternalCode)
class UserExternalCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'external_system')
    list_select_related = ('user', 'external_system')
    raw_id_fields = ('user', 'external_system')


@admin.register(GenericExternalCode)
class GenericExternalCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'external_system', 'object_type', 'object')
    list_filter = (('external_system', CustomRelatedOnlyDropdownFilter), ('object_type', CustomRelatedOnlyDropdownFilter))
