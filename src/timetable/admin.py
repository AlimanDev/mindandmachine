from src.timetable.forms import ExchangeSettingsForm
from django.contrib import admin
from django.utils.translation import gettext as _
from rangefilter.filter import DateRangeFilter, DateTimeRangeFilter
from django_admin_listfilter_dropdown.filters import RelatedOnlyDropdownFilter, DropdownFilter, ChoiceDropdownFilter



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
)


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
    search_fields = ('employment__user__last_name', 'work_type__name', 'id')
    list_filter = ('work_type__shop',)

    @staticmethod
    def worker(instance: EmploymentWorkType):
        user = instance.employment.user
        return f"({user.id}) {user.last_name} {user.first_name}"

    @staticmethod
    def work_type_name(instance: EmploymentWorkType):
        return instance.work_type.work_type_name.name


@admin.register(WorkerConstraint)
class WorkerConstraintAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'weekday', 'tm', 'id')
    search_fields = ('worker__last_name',)
    list_filter = ('shop',)

    @staticmethod
    def worker_last_name(instance: WorkerConstraint):
        return instance.worker.last_name


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
        ('shop', RelatedOnlyDropdownFilter), 
        ('type', ChoiceDropdownFilter), 
        ('dttm_modified', DateTimeRangeFilter), 
        ('created_by', RelatedOnlyDropdownFilter),
    )
    raw_id_fields = ('parent_worker_day', 'employment', 'created_by', 'last_edited_by', 'employee', 'shop')
    list_select_related = ('employee__user', 'shop', 'created_by')
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
    list_filter = ('worker_day__shop',)
    raw_id_fields = ('worker_day', 'work_type')
    list_select_related = (
        'worker_day__employee__user', 'worker_day__shop', 'work_type')

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
    list_filter = ('shop',)

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
    list_filter = ('type', 'verified', 'type')


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
