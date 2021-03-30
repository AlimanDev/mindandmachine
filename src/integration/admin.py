from django.contrib import admin
from src.integration.models import (
    ExternalSystem,
    ShopExternalCode,
    UserExternalCode,
)

@admin.register(ExternalSystem)
class ExternalSystemAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')


@admin.register(ShopExternalCode)
class ShopExternalCodeAdmin(admin.ModelAdmin):
    list_display = ('shop', 'code', 'external_system')


@admin.register(UserExternalCode)
class UserExternalCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'external_system')