from django.contrib import admin
from django.forms import Form
from django.utils.translation import gettext as _
from import_export.admin import ExportActionMixin, ImportMixin
from rangefilter.filter import DateRangeFilter, DateTimeRangeFilter
from src.base.admin import BaseNotWrapRelatedModelaAdmin
from src.base.admin_filters import CustomRelatedDropdownFilter, CustomRelatedOnlyDropdownFilter

from src.base.forms import (
    CustomImportFunctionGroupForm,
    CustomConfirmImportFunctionGroupForm,
)
from src.recognition.admin import RelatedOnlyDropdownNameOrderedFilter
from src.timetable.forms import ExchangeSettingsForm, GroupWorkerDayPermissionForm
from src.timetable.models import (
    Cashbox,
    EmploymentWorkType,
    WorkerDayCashboxDetails,
    Notifications,
    Slot,
    UserWeekdaySlot,
    WorkerConstraint,
    ShopMonthStat,
    WorkerDayChangeRequest,
    AttendanceRecords,
    ExchangeSettings,
    Event,
    WorkerDay,
    WorkTypeName,
    WorkerDayType,
    GroupWorkerDayPermission,
    WorkerDayPermission,
    TimesheetItem,
)
from .resources import GroupWorkerDayPermissionResource


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ('name', 'work_type_name', 'shop_title', 'parent_title', 'tm_start', 'tm_end', 'id')
    search_fields = ('name', 'shop__name', 'shop__parent__name', 'id')
    list_filter = ('shop',)

    @staticmethod
    def shop_title(instance: Slot):
        return instance.shop.name

    @staticmethod
    def parent_title(instance: Slot):
        return instance.shop.parent_title()

    @staticmethod
    def work_type_name(instance: Slot):
        if instance.work_type:
            return instance.work_type.work_type_name.name


@admin.register(UserWeekdaySlot)
class UserWeekDaySlotAdmin(admin.ModelAdmin):
    list_display = ('worker_first_name', 'worker_last_name', 'shop_title', 'parent_title', 'slot_name',
                    'weekday', 'id')
    search_fields = ('worker__first_name', 'worker__last_name', 'slot__shop__name', 'slot__shop__parent__name',
                     'slot__name', 'id')
    list_filter = ('slot__shop',)

    @staticmethod
    def worker_first_name(instance: UserWeekdaySlot):
        return instance.worker.first_name

    @staticmethod
    def slot_name(instance: UserWeekdaySlot):
        return instance.slot.name

    @staticmethod
    def worker_last_name(instance: UserWeekdaySlot):
        return instance.worker.last_name

    @staticmethod
    def shop_title(instance: UserWeekdaySlot):
        return instance.worker.shop.name

    @staticmethod
    def parent_title(instance: UserWeekdaySlot):
        return instance.worker.shop.parent_title()


@admin.register(Cashbox)
class CashboxAdmin(admin.ModelAdmin):
    list_display = ('type_name', 'shop_title', 'parent_title', 'id', 'name')
    search_fields = ('type__name', 'type__shop__name', 'type__shop__parent__name', 'id')
    list_filter = ('type__shop',)

    @staticmethod
    def type_name(instance: Cashbox):
        return instance.type.name

    @staticmethod
    def shop_title(instance: Cashbox):
        return instance.type.shop.name

    @staticmethod
    def parent_title(instance: Cashbox):
        return instance.type.shop.parent_title()


@admin.register(EmploymentWorkType)
class WorkerCashboxInfoAdmin(admin.ModelAdmin):
    list_display = ('worker', 'work_type_name', 'id')
    search_fields = ('employment__employee__user__last_name', 'work_type__work_type_name__name', 'id')
    list_filter = (('work_type__shop', RelatedOnlyDropdownNameOrderedFilter),)
    list_select_related = ('work_type__work_type_name', 'work_type__shop', 'employment__employee__user')
    raw_id_fields = ('employment', 'work_type')

    @staticmethod
    def worker(instance: EmploymentWorkType):
        user = instance.employment.employee.user
        return f"({user.id}) {user.last_name} {user.first_name}"

    @staticmethod
    def work_type_name(instance: EmploymentWorkType):
        return instance.work_type.work_type_name.name


@admin.register(WorkerConstraint)
class WorkerConstraintAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'weekday', 'tm', 'id')
    search_fields = ('employment__employee__user__last_name',)
    list_filter = (('shop', RelatedOnlyDropdownNameOrderedFilter),)
    raw_id_fields = ('employment', 'shop')
    list_select_related = ('employment__employee__user',)

    @staticmethod
    def worker_last_name(instance: WorkerConstraint):
        return instance.employment.employee.user.last_name


@admin.register(WorkerDay)
class WorkerDayAdmin(admin.ModelAdmin):
    list_display = (
        'shop_title', 
        'worker_last_name', 
        'graph_type', 
        'type', 
        'dt_formated', 
        'tm_work_start',
        'tm_work_end', 
        'dttm_modified', 
        'created_by_last_name',
        'id', 
    )
    search_fields = ('employee__user__last_name', 'shop__name', 'shop__parent__name', 'id', 'dt')
    list_filter = (
        ('dt', DateRangeFilter),
        'is_fact',
        'is_approved',
        ('shop', CustomRelatedOnlyDropdownFilter),
        ('type', CustomRelatedDropdownFilter),
        ('dttm_modified', DateTimeRangeFilter),
        ('created_by', CustomRelatedOnlyDropdownFilter),
    )
    raw_id_fields = ('parent_worker_day', 'employment', 'created_by', 'last_edited_by', 'employee', 'shop', 'type', 'closest_plan_approved')
    list_select_related = ('employee__user', 'shop', 'created_by', 'last_edited_by', 'parent_worker_day', 'type', 'closest_plan_approved')
    readonly_fields = ('dttm_modified',)
    change_list_template = 'worker_day_change_list.html'

    @staticmethod
    def worker_last_name(instance: WorkerDay):
        return instance.employee.user.last_name if getattr(instance.employee, 'user', None) else 'Нет работника'

    @staticmethod
    def shop_title(instance: WorkerDay):
        return instance.shop.name if instance.shop else '-'

    @staticmethod
    def tm_work_start(instance: WorkerDay):
        return instance.dttm_work_start.strftime('%H:%M:%S') if instance.dttm_work_start else '-'
    
    @staticmethod
    def tm_work_end(instance: WorkerDay):
        return instance.dttm_work_end.strftime('%H:%M:%S') if instance.dttm_work_end else '-'

    @staticmethod
    def graph_type(instance: WorkerDay):
        graph_type = _('Not approved plan')
        if instance.is_approved and instance.is_plan:
            graph_type = _('Approved plan')
        elif instance.is_approved and instance.is_fact:
            graph_type = _('Approved fact')
        elif instance.is_fact:
            graph_type = _('Not approved fact')
        return graph_type

    def dt_formated(self, obj):
        return obj.dt.strftime('%d.%m.%Y')
    
    dt_formated.short_description = 'dt'

    def created_by_last_name(self, instance: WorkerDay):
        return instance.created_by.last_name if instance.created_by else 'Автоматически'
    
    created_by_last_name.short_description = 'created by'


@admin.register(WorkerDayCashboxDetails)
class WorkerDayCashboxDetailsAdmin(admin.ModelAdmin):
    # todo: нет нормального отображения для конкретного pk(скорее всего из-за harakiri time в настройках uwsgi)
    list_display = ('worker_last_name', 'shop_title', 'worker_day_dt', 'on_work_type', 'id')
    search_fields = ('worker_day__employee__user__last_name', 'worker_day__shop__name', 'id')
    list_filter = (('worker_day__shop', RelatedOnlyDropdownNameOrderedFilter),)
    raw_id_fields = ('worker_day', 'work_type')
    list_select_related = (
        'worker_day__employee__user', 'worker_day__shop', 'work_type__work_type_name')

    @staticmethod
    def worker_last_name(instance: WorkerDayCashboxDetails):
        return instance.worker_day.employee.user.last_name if instance.worker_day and instance.worker_day.employee.user else ''

    @staticmethod
    def shop_title(instance: WorkerDayCashboxDetails):
        return instance.worker_day.shop.name if instance.worker_day and instance.worker_day.shop else ''

    @staticmethod
    def worker_day_dt(instance: WorkerDayCashboxDetails):
        return instance.worker_day.dt if instance.worker_day else ''

    @staticmethod
    def on_work_type(instance: WorkerDayCashboxDetails):
        return instance.work_type.work_type_name.name if instance.work_type else ''


@admin.register(Notifications)
class NotificationsAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'shop_title', 'parent_title', 'dttm_added', 'id')
    search_fields = ('worker_last_name', 'shop_title', 'parent_title', 'id')
    list_filter = ('shop',)

    @staticmethod
    def worker_last_name(instance: ShopMonthStat):
        return instance.to_worker.last_name

    @staticmethod
    def shop_title(instance: ShopMonthStat):
        return instance.shop.name

    @staticmethod
    def parent_title(instance: ShopMonthStat):
        return instance.shop.parent_title()


@admin.register(ShopMonthStat)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop_title', 'parent_title', 'dt', 'status', 'dttm_status_change',
                    'fot', 'idle', 'lack', 'workers_amount', 'revenue', 'fot_revenue',)
    search_fields = ('shop__name', 'shop__parent__name')
    list_select_related = ('shop', 'shop__parent')
    list_filter = (('shop', RelatedOnlyDropdownNameOrderedFilter),)
    raw_id_fields = ('shop',)

    @staticmethod
    def parent_title(instance: ShopMonthStat):
        return instance.shop.parent_title()

    @staticmethod
    def shop_title(instance: ShopMonthStat):
        return instance.shop.name


@admin.register(WorkerDayChangeRequest)
class WorkerDayChangeRequestAdmin(admin.ModelAdmin):
    pass


@admin.register(AttendanceRecords)
class AttendanceRecordsAdmin(admin.ModelAdmin):
    list_display = ('id', 'dttm', 'type',)
    list_filter = ('type', 'verified',)
    raw_id_fields = ('user', 'employee', 'shop')


@admin.register(ExchangeSettings)
class ExchangeSettingsAdmin(admin.ModelAdmin):
    form = ExchangeSettingsForm


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    pass


@admin.register(WorkTypeName)
class WorkTypeNameAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(WorkerDayType)
class WorkerDayTypeAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'name',
        'use_in_plan',
        'use_in_fact',
        'excel_load_code',
        'is_dayoff',
        'is_work_hours',
        'is_reduce_norm',
        'is_system',
        'show_stat_in_days',
        'show_stat_in_hours',
        'ordering',
        'is_active',
    )
    search_fields = ('name', 'short_name', 'code')

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system:
            return False
        return super(WorkerDayTypeAdmin, self).has_delete_permission(request, obj=obj)


@admin.register(GroupWorkerDayPermission)
class GroupWorkerDayPermissionAdmin(ImportMixin, ExportActionMixin, BaseNotWrapRelatedModelaAdmin):
    not_wrap_fields = ['worker_day_permission']
    list_display = ('id', 'group', 'worker_day_permission', 'limit_days_in_past', 'limit_days_in_future')
    list_editable = ('limit_days_in_past', 'limit_days_in_future')
    list_filter = [
        ('group', CustomRelatedDropdownFilter),
        'worker_day_permission__action',
        'worker_day_permission__graph_type',
        ('worker_day_permission__wd_type', CustomRelatedDropdownFilter),
    ]
    list_select_related = ('group', 'worker_day_permission__wd_type')
    resource_class = GroupWorkerDayPermissionResource
    form = GroupWorkerDayPermissionForm

    def get_import_form(self):
        return CustomImportFunctionGroupForm

    def get_confirm_import_form(self):
        return CustomConfirmImportFunctionGroupForm

    def get_form_kwargs(self, form, *args, **kwargs):
        if isinstance(form, Form) and form.is_valid():
            groups = form.cleaned_data['groups']
            kwargs.update({'groups': groups.values_list('id', flat=True)})
        return kwargs

    def get_import_data_kwargs(self, request, *args, **kwargs):
        form = kwargs.get('form')
        if form and form.is_valid():
            groups = form.cleaned_data['groups']
            kwargs.update({'groups': groups.values_list('id', flat=True)})
        return super().get_import_data_kwargs(request, *args, **kwargs)


@admin.register(TimesheetItem)
class TimesheetItemAdmin(admin.ModelAdmin):
    save_as = True
    raw_id_fields = ('shop', 'position', 'work_type_name', 'employee')
    list_filter = (
        ('shop', CustomRelatedDropdownFilter),
        ('position', CustomRelatedDropdownFilter),
        ('work_type_name', CustomRelatedDropdownFilter),
        ('employee', CustomRelatedDropdownFilter),
        'timesheet_type',
        'day_type',
    )
    list_display = (
        'id',
        'timesheet_type',
        'employee',
        'shop',
        'position',
        'work_type_name',
        'day_type',
        'day_hours',
        'night_hours',
    )
