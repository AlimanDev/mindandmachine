from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.db.models.query import QuerySet

from src.base.admin_filters import RelatedOnlyDropdownNameOrderedFilter
from src.forecast.models import (
    PeriodClients,
    WorkType,
    OperationType,
    OperationTypeName,
    LoadTemplate,
    OperationTypeTemplate,
    OperationTypeRelation,
    Receipt,
)
from src.forecast.forms import LoadTemplateAdminForm
from src.forecast.load_template import tasks


@admin.register(OperationType)
class OperationTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'work_type_name', 'operation_type_name', 'period_demand_params', 'shop')
    list_filter = (
        ('shop', RelatedOnlyDropdownNameOrderedFilter),
    )
    search_fields = ('shop__name', 'shop__code', 'operation_type_name__name', 'operation_type_name__code')
    raw_id_fields = ('shop', 'work_type', 'operation_type_name')
    list_select_related = ('work_type__work_type_name', 'operation_type_name')
    save_as = True

    @staticmethod
    def work_type_name(instance: OperationType):
        return instance.work_type.work_type_name.name if instance.work_type else 'Без типа работ'
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('operation_type_name', 'work_type')
        return self.readonly_fields


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ('work_type_name', 'shop_title', 'parent_title', 'dttm_added', 'id')
    search_fields = ('work_type_name__name', 'shop__name', 'shop__parent__name', 'id')
    list_filter = (
        ('work_type_name', RelatedOnlyDropdownNameOrderedFilter), 
        ('shop', RelatedOnlyDropdownNameOrderedFilter),
    )
    raw_id_fields = ('shop', 'work_type_name')
    list_select_related = ('work_type_name', 'shop', 'shop__parent')
    save_as = True

    @staticmethod
    def shop_title(instance: WorkType):
        return instance.shop.name

    @staticmethod
    def parent_title(instance: WorkType):
        return instance.shop.parent_title()
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('work_type_name',)
        return self.readonly_fields


@admin.register(PeriodClients)
class PeriodClientsAdmin(admin.ModelAdmin):
    list_display = ('id', 'operation_type_name', 'value', 'dttm_forecast', 'type',)
    search_fields = ('dttm_forecast', 'id')
    list_filter = (
        ('operation_type__operation_type_name__work_type_name', RelatedOnlyDropdownNameOrderedFilter), 
        'type'
    )
    list_select_related = ('operation_type__operation_type_name',)
    raw_id_fields = ('operation_type',)
    change_list_template = 'period_clients_change_list.html'

    @staticmethod
    def operation_type_name(instance: PeriodClients):
        return instance.operation_type.operation_type_name.name or instance.operation_type.id


@admin.register(OperationTypeName)
class OperationTypeNameAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'do_forecast', 'work_type_name')
    search_fields = ('name',)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('work_type_name',)
        return self.readonly_fields


@admin.register(LoadTemplate)
class LoadTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)
    form = LoadTemplateAdminForm
    change_list_template = 'load_template_change_list.html'
    actions = ['apply_load_template']

    @admin.action(description=_('Apply load templates to shops'))
    def apply_load_template(self, request, queryset: QuerySet):
        for load_template in queryset:
            tasks.apply_load_template_to_shops.delay(load_template.id)
        self.message_user(request, _('Applying load templates started'), messages.SUCCESS)


@admin.register(OperationTypeTemplate)
class OperationTypeTemplateAdmin(admin.ModelAdmin):
    list_display = ('operation_name', 'load_template_name')
    list_select_related = ('operation_type_name', 'load_template')
    search_fields = ('operation_type_name__name', 'load_template__name')

    @staticmethod
    def operation_name(obj: OperationTypeTemplate):
        return obj.operation_type_name.name

    @staticmethod
    def load_template_name(obj: OperationTypeTemplate):
        return obj.load_template.name

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('operation_type_name', 'load_template')
        return self.readonly_fields


@admin.register(OperationTypeRelation)
class OperationTypeRelationAdmin(admin.ModelAdmin):
    list_display = ('base_name', 'depended_name', 'type')
    list_select_related = ('base__operation_type_name', 'depended__operation_type_name')
    list_filter = (
        ('base__load_template', RelatedOnlyDropdownNameOrderedFilter),
    )

    @staticmethod
    def base_name(obj: OperationTypeRelation):
        return obj.base.operation_type_name.name

    @staticmethod
    def depended_name(obj: OperationTypeRelation):
        return obj.depended.operation_type_name.name

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('base', 'depended', 'type')
        return self.readonly_fields


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop_id', 'dttm_modified', 'code')