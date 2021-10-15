from django.contrib import admin
from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin, PolymorphicChildModelFilter

from .models import (
    ImportJob,
    ExportJob,
    BaseFilesystemConnector,
    LocalFilesystemConnector,
    FtpFilesystemConnector,
    ImportStrategy,
    SystemImportStrategy,
    ExportStrategy,
    SystemExportStrategy,
)


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'base_path')


@admin.register(ExportJob)
class ExportJobAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'base_path')


class FilesystemConfigChildAdmin(PolymorphicChildModelAdmin):
    base_model = BaseFilesystemConnector


@admin.register(LocalFilesystemConnector)
class LocalFilesystemConnectorAdmin(FilesystemConfigChildAdmin):
    pass


@admin.register(FtpFilesystemConnector)
class FtpFilesystemConnectorAdmin(FilesystemConfigChildAdmin):
    list_display = ('host', 'username')


@admin.register(BaseFilesystemConnector)
class BaseFilesystemConnectorAdmin(PolymorphicParentModelAdmin):
    base_model = BaseFilesystemConnector
    child_models = (LocalFilesystemConnector, FtpFilesystemConnector)
    base_list_display = ('name', 'default_base_path')
    list_filter = (PolymorphicChildModelFilter,)


class ImportStrategyChildAdmin(PolymorphicChildModelAdmin):
    base_model = ImportStrategy


@admin.register(SystemImportStrategy)
class SystemImportStrategyAdmin(ImportStrategyChildAdmin):
    list_display = ('name',)


@admin.register(ImportStrategy)
class ImportStrategyAdmin(PolymorphicParentModelAdmin):
    base_model = ImportStrategy
    child_models = (SystemImportStrategy,)
    base_list_display = ('name',)
    list_filter = (PolymorphicChildModelFilter,)


class ExportStrategyChildAdmin(PolymorphicChildModelAdmin):
    base_model = ExportStrategy


@admin.register(SystemExportStrategy)
class SystemExportStrategyAdmin(ExportStrategyChildAdmin):
    list_display = ('name',)


@admin.register(ExportStrategy)
class ExportStrategyAdmin(PolymorphicParentModelAdmin):
    base_model = ExportStrategy
    child_models = (SystemExportStrategy,)
    base_list_display = ('name',)
    list_filter = (PolymorphicChildModelFilter,)
