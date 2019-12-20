from django.contrib import admin
from src.forecast.models import (
    PeriodClients,
    PeriodDemandChangeLog,
    WorkType,
    PeriodDemand,
    OperationType,
    OperationTemplate,
)


@admin.register(OperationType)
class OperationTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'work_type_name', 'name', 'speed_coef', 'do_forecast', 'period_demand_params')
    list_filter = ('work_type__shop',)
    search_fields = ('work_type__shop', 'name')

    @staticmethod
    def work_type_name(instance: OperationType):
        return instance.work_type.name if instance.work_type else 'Без типа работ'


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop_title', 'parent_title', 'dttm_added', 'id')
    search_fields = ('name', 'shop__title', 'shop__parent__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def shop_title(instance: WorkType):
        return instance.shop.title

    @staticmethod
    def parent_title(instance: WorkType):
        return instance.shop.parent_title()


class PeriodDemandAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation_type_name', 'value', 'dttm_forecast', 'type',)
    search_fields = ('dttm_forecast', 'id')
    list_filter = ('operation_type__work_type_id', 'type')

    @staticmethod
    def operation_type_name(instance: PeriodDemand):
        return instance.operation_type.name or instance.operation_type.id


@admin.register(PeriodClients)
class PeriodClientsAdmin(PeriodDemandAdmin):
    pass


@admin.register(PeriodDemandChangeLog)
class PeriodDemandChangeLogAdmin(admin.ModelAdmin):
    list_display = ('operation_type_name', 'dttm_from', 'dttm_to')
    search_fields = ('operation_type_name', 'operation_type__work_type__shop__title', 'id')
    list_filter = ('operation_type__work_type__shop', )

    @staticmethod
    def operation_type_name(instance: PeriodDemandChangeLog):
        return instance.operation_type.name

    @staticmethod
    def shop_title(instance: PeriodDemandChangeLog):
        return instance.operation_type.work_type.shop.title


@admin.register(OperationTemplate)
class OperationTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'operation_type')
    list_filter = ('operation_type', )
    search_fields = ('name',)

