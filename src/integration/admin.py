from django.contrib import admin

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


@admin.register(UserExternalCode)
class UserExternalCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'external_system')


@admin.register(GenericExternalCode)
class GenericExternalCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'external_system', 'object_type', 'object')
    list_filter = ('external_system', 'object_type')
