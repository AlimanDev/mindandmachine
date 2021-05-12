from django.contrib import admin

from src.base.models import (
    Employment,
    User,
    Shop,
    ShopSettings,
    Group,
    FunctionGroup,
    WorkerPosition,
    Region,
    ProductionDay,
    Network,
    Break,
    SAWHSettings,
    SAWHSettingsMapping,
    ShopSchedule,
    Employee,
    NetworkConnect,
)
from src.timetable.models import GroupWorkerDayPermission
from src.base.forms import NetworkAdminForm, ShopAdminForm, ShopSettingsAdminForm, BreakAdminForm

@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'logo')
    form = NetworkAdminForm

@admin.register(NetworkConnect)
class NetworkConnectAdmin(admin.ModelAdmin):
    list_display = ('id', 'outsourcing', 'client')
    list_select_related = ('outsourcing', 'client')


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')


@admin.register(WorkerPosition)
class WorkerPositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')
    search_fields = ('name', 'code')


@admin.register(User)
class QsUserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'shop_name', 'id', 'username',)
    search_fields = ('first_name', 'last_name', 'id', 'username',)

    # list_filter = ('employment__shop', )

    # list_display = ('first_name', 'last_name', 'employment__shop__name', 'parent_title', 'work_type_name', 'id')
    # search_fields = ('first_name', 'last_name', 'employment__shop__parent__name', 'workercashboxinfo__work_type__name', 'id')

    # @staticmethod
    # def parent_title(instance: User):
    #     if instance.shop and instance.shop.parent:
    #         return instance.shop.parent_title()
    #     return 'без магазина'

    @staticmethod
    def shop_name(instance: User):
        res = ', '.join(
            list(Employment.objects.get_active(employee__user=instance).values_list('shop__name', flat=True).distinct()))
        return res

    '''
    @staticmethod
    def work_type_name(instance: User):
        cashboxinfo_set = instance.workercashboxinfo_set.all().select_related('work_type')
        return ' '.join(['"{}"'.format(cbi.work_type.name) for cbi in cashboxinfo_set])
    '''


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'tabel_code')
    search_fields = ('id', 'user__last_name', 'user__first_name', 'user__username', 'tabel_code')
    raw_id_fields = ('user',)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_title', 'id', 'code')
    search_fields = ('name', 'parent__name', 'id', 'code')
    raw_id_fields = ('director',)
    form = ShopAdminForm

    @staticmethod
    def parent_title(instance: Shop):
        return instance.parent_title()


@admin.register(ShopSettings)
class ShopSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('id', 'name')
    form = ShopSettingsAdminForm


class GroupWorkerDayPermissionInline(admin.TabularInline):
    model = GroupWorkerDayPermission
    extra = 0

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('group', 'worker_day_permission')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_dispaly = ('id', 'dttm_added', 'name', 'subordinates')
    list_filter = ('id', 'name')
    inlines = (
        GroupWorkerDayPermissionInline,
    )
    save_as = True

    def get_actions(self, request):
        from src.util.wd_perms.utils import WdPermsHelper
        actions = super().get_actions(request)
        actions.update(WdPermsHelper.get_preset_actions())
        return actions


@admin.register(FunctionGroup)
class FunctionGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'access_type', 'group', 'func', 'method', 'level_down', 'level_up')
    list_filter = ('access_type', 'group', 'func')
    search_fields = ('id',)


@admin.register(Employment)
class EmploymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'employee', 'function_group', 'dt_hired_formated', 'dt_fired_formated')
    list_select_related = ('employee', 'employee__user', 'shop', 'function_group')
    list_filter = ('shop', 'employee')
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 'shop__name', 'shop__parent__name', 'employee__tabel_code')
    raw_id_fields = ('shop', 'employee', 'position')

    def dt_hired_formated(self, obj):
        return obj.dt_hired.strftime('%d.%m.%Y') if obj.dt_hired else '-'
    
    dt_hired_formated.short_description = 'dt hired'

    def dt_fired_formated(self, obj):
        return obj.dt_fired.strftime('%d.%m.%Y') if obj.dt_fired else '-'
    
    dt_fired_formated.short_description = 'dt fired'


@admin.register(ProductionDay)
class ProductionDayAdmin(admin.ModelAdmin):
    list_display = ('dt', 'type')


@admin.register(Break)
class BreakAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')
    search_fields = ('name',)
    form = BreakAdminForm


class SAWHSettingsMappingInline(admin.StackedInline):
    model = SAWHSettingsMapping
    extra = 0

    filter_horizontal = ('shops', 'positions', 'exclude_positions')


@admin.register(SAWHSettings)
class SAWHSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'code',
        'type',
    )

    inlines = (
        SAWHSettingsMappingInline,
    )

    def get_queryset(self, request):
        return super(SAWHSettingsAdmin, self).get_queryset(request).filter(network_id=request.user.network_id)


@admin.register(ShopSchedule)
class ShopScheduleAdmin(admin.ModelAdmin):
    raw_id_fields = ('shop',)
    list_filter = ('dt', 'shop',)
    list_display = ('dt', 'shop', 'modified_by', 'type', 'opens', 'closes')
    readonly_fields = ('modified_by',)

    def save_model(self, request, obj, form, change):
        obj.modified_by = request.user
        obj.save(recalc_wdays=True)
