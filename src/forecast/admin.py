from django.contrib import admin
from src.forecast.models import (
    PeriodClients,
    PeriodDemandChangeLog,
    WorkType,
    OperationType,
    OperationTemplate,
    OperationTypeName,
    LoadTemplate,
    OperationTypeTemplate,
    OperationTypeRelation,
    Receipt,
)


@admin.register(OperationType)
class OperationTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'work_type_name', 'operation_type_name', 'period_demand_params', 'shop')
    list_filter = ('shop',)
    search_fields = ('shop', 'name')

    @staticmethod
    def work_type_name(instance: OperationType):
        return instance.work_type.work_type_name.name if instance.work_type else 'Без типа работ'


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ('work_type_name', 'shop_title', 'parent_title', 'dttm_added', 'id')
    search_fields = ('work_type_name__name', 'shop__title', 'shop__parent__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def shop_title(instance: WorkType):
        return instance.shop.name

    @staticmethod
    def parent_title(instance: WorkType):
        return instance.shop.parent_title()


@admin.register(PeriodClients)
class PeriodClientsAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation_type_name', 'value', 'dttm_forecast', 'type',)
    search_fields = ('dttm_forecast', 'id')
    list_filter = ('operation_type__work_type_id', 'type')

    @staticmethod
    def operation_type_name(instance: PeriodClients):
        return instance.operation_type.operation_type_name.name or instance.operation_type.id


@admin.register(PeriodDemandChangeLog)
class PeriodDemandChangeLogAdmin(admin.ModelAdmin):
    list_display = ('operation_type_name', 'dttm_from', 'dttm_to')
    search_fields = ('operation_type_name', 'operation_type__shop__title', 'id')
    list_filter = ('operation_type__shop', )

    @staticmethod
    def operation_type_name(instance: PeriodDemandChangeLog):
        return instance.operation_type.name

    @staticmethod
    def shop_title(instance: PeriodDemandChangeLog):
        return instance.operation_type.work_type.shop.name


@admin.register(OperationTemplate)
class OperationTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'operation_type')
    list_filter = ('operation_type', )
    search_fields = ('name',)


@admin.register(OperationTypeName)
class OperationTypeNameAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'do_forecast', 'work_type_name')
    search_fields = ('name',)


@admin.register(LoadTemplate)
class LoadTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(OperationTypeTemplate)
class OperationTypeTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation_type_name',)
    search_fields = ('operation_type_name__name', 'operation_type_name__work_type_name__name')


@admin.register(OperationTypeRelation)
class OperationTypeRelationAdmin(admin.ModelAdmin):
    list_display = ('id', 'base_id', 'depended_id', 'formula')



@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop_id', 'dttm_modified', 'code')