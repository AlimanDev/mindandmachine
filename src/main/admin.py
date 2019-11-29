from django.contrib import admin
from src.db.models import (
    Employment,
    User,
    Shop,
    WorkerDay,
    PeriodClients,
    PeriodDemandChangeLog,
    WorkType,
    Cashbox,
    WorkerCashboxInfo,
    WorkerDayCashboxDetails,
    Notifications,
    Slot,
    PeriodDemand,
    UserWeekdaySlot,
    WorkerConstraint,
    Timetable,
    ProductionDay,
    ProductionMonth,
    WorkerMonthStat,
    Group,
    FunctionGroup,
    WorkerPosition,
    OperationType,
    WorkerDayChangeRequest,
    AttendanceRecords,
    ExchangeSettings,
    Event,
    OperationTemplate,
)


@admin.register(WorkerPosition)
class WorkerPositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title')
    search_fields = ('title',)


@admin.register(OperationType)
class OperationTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'work_type_name', 'name', 'speed_coef', 'do_forecast', 'period_demand_params')
    list_filter = ('work_type__shop',)
    search_fields = ('work_type__shop', 'name')

    @staticmethod
    def work_type_name(instance: OperationType):
        return instance.work_type.name if instance.work_type else 'Без типа работ'


@admin.register(User)
class QsUserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'shop_title', 'id')
    search_fields = ('first_name', 'last_name', 'shop_title', 'workercashboxinfo__work_type__name', 'id')
    # list_filter = ('employment__shop', )

    # list_display = ('first_name', 'last_name', 'employment__shop__title', 'parent_title', 'work_type_name', 'id')
    # search_fields = ('first_name', 'last_name', 'employment__shop__parent__title', 'workercashboxinfo__work_type__name', 'id')

    # @staticmethod
    # def parent_title(instance: User):
    #     if instance.shop and instance.shop.parent:
    #         return instance.shop.parent_title()
    #     return 'без магазина'

    @staticmethod
    def shop_title(instance: User):
        res = ', '.join(i.shop.title for i in instance.employments.all().select_related('shop'))
        return res
    '''
    @staticmethod
    def work_type_name(instance: User):
        cashboxinfo_set = instance.workercashboxinfo_set.all().select_related('work_type')
        return ' '.join(['"{}"'.format(cbi.work_type.name) for cbi in cashboxinfo_set])
    '''

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('title', 'parent_title', 'id')
    search_fields = ('title', 'parent__title', 'id')

    @staticmethod
    def parent_title(instance: Shop):
        return instance.parent_title()


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


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ('name', 'work_type_name', 'shop_title', 'parent_title', 'tm_start', 'tm_end', 'id')
    search_fields = ('name', 'shop__title', 'shop__parent__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def shop_title(instance: Slot):
        return instance.shop.title

    @staticmethod
    def parent_title(instance: Slot):
        return instance.shop.parent_title()

    @staticmethod
    def work_type_name(instance: Slot):
        if instance.work_type:
            return instance.work_type.name


@admin.register(UserWeekdaySlot)
class UserWeekDaySlotAdmin(admin.ModelAdmin):
    list_display = ('worker_first_name', 'worker_last_name', 'shop_title', 'parent_title', 'slot_name',
                    'weekday', 'id')
    search_fields = ('worker__first_name','worker__last_name', 'slot__shop__title', 'slot__shop__parent__title',
                     'slot__name', 'id')
    list_filter = ('slot__shop', )

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
        return instance.worker.shop.title

    @staticmethod
    def parent_title(instance: UserWeekdaySlot):
        return instance.worker.shop.parent_title()


@admin.register(Cashbox)
class CashboxAdmin(admin.ModelAdmin):
    list_display = ('type_name', 'shop_title', 'parent_title', 'id', 'number')
    search_fields = ('type__name', 'type__shop__title', 'type__shop__parent__title', 'id')
    list_filter = ('type__shop', )

    @staticmethod
    def type_name(instance: Cashbox):
        return instance.type.name

    @staticmethod
    def shop_title(instance: Cashbox):
        return instance.type.shop.title

    @staticmethod
    def parent_title(instance: Cashbox):
        return instance.type.shop.parent_title()


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


@admin.register(WorkerCashboxInfo)
class WorkerCashboxInfoAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'work_type_name', 'id')
    search_fields = ('worker__last_name', 'work_type__name', 'id')
    list_filter = ('work_type__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerCashboxInfo):
        return instance.worker.last_name

    @staticmethod
    def work_type_name(instance: WorkerCashboxInfo):
        return instance.work_type.name


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
    list_display = ('worker_last_name', 'shop_title', 'parent_title', 'dt', 'type', 'id', 'dttm_work_start',
                    'dttm_work_end')
    search_fields = ('worker__last_name', 'shop_title', 'parent_title', 'id', 'dt')
    list_filter = ('shop', 'type')
    raw_id_fields = ('parent_worker_day',)
    list_select_related = ('worker', 'shop')

    @staticmethod
    def worker_last_name(instance: WorkerConstraint):
        return instance.worker.last_name

    @staticmethod
    def shop_title(instance: WorkerDay):
        return instance.shop.title if instance.shop else ''


    @staticmethod
    def parent_title(instance: Timetable):
        return instance.shop.parent_title() if instance.shop else ''


@admin.register(WorkerDayCashboxDetails)
class WorkerDayCashboxDetailsAdmin(admin.ModelAdmin):
    # todo: нет нормального отображения для конкретного pk(скорее всего из-за harakiri time в настройках uwsgi)
    # todo: upd: сервак просто падает если туда зайти
    list_display = ('worker_last_name', 'shop_title', 'worker_day_dt', 'on_work_type', 'id', 'dttm_from', 'dttm_to')
    search_fields = ('worker_day__worker__last_name', 'worker_day__shop__title', 'id')
    list_filter = ('worker_day__shop', 'is_vacancy')
    raw_id_fields = ('worker_day',)
    list_select_related = (
        'worker_day__worker', 'worker_day__shop', 'work_type')

    @staticmethod
    def worker_last_name(instance: WorkerDayCashboxDetails):
        return instance.worker_day.worker.last_name if instance.worker_day else ''

    @staticmethod
    def shop_title(instance: WorkerDayCashboxDetails):
        return instance.worker_day.worker.shop.title if instance.worker_day else ''

    @staticmethod
    def worker_day_dt(instance: WorkerDayCashboxDetails):
        return instance.worker_day.dt if instance.worker_day else instance.dttm_from.date()

    @staticmethod
    def on_work_type(instance: WorkerDayCashboxDetails):
        return instance.work_type.name if instance.work_type else ''


@admin.register(Notifications)
class NotificationsAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'shop_title', 'parent_title', 'dttm_added', 'id')
    search_fields = ('worker_last_name', 'shop_title', 'parent_title', 'id')
    list_filter = ('shop',)

    @staticmethod
    def worker_last_name(instance: Timetable):
        return instance.to_worker.last_name

    @staticmethod
    def shop_title(instance: Timetable):
        return instance.shop.title

    @staticmethod
    def parent_title(instance: Timetable):
        return instance.shop.parent_title()


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop_title', 'parent_title', 'dt', 'status', 'dttm_status_change',
                    'fot', 'idle', 'lack', 'workers_amount', 'revenue', 'fot_revenue',)
    search_fields = ('shop__title', 'shop__parent__title')
    list_filter = ('shop',)

    @staticmethod
    def parent_title(instance: Timetable):
        return instance.shop.parent_title()

    @staticmethod
    def shop_title(instance: Timetable):
        return instance.shop.title


@admin.register(ProductionDay)
class ProductionDayAdmin(admin.ModelAdmin):
    list_display = ('dt', 'type')


@admin.register(WorkerMonthStat)
class WorkerMonthStatAdmin(admin.ModelAdmin):
    list_display = ('worker_id', 'month')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_dispaly = ('id', 'dttm_added', 'name', 'subordinates')
    list_filter = ('id', 'name')


@admin.register(FunctionGroup)
class FunctionGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'access_type', 'group', 'func', 'level_down', 'level_up')
    list_filter = ('access_type', 'group', 'func')
    search_fields = ('id',)



@admin.register(WorkerDayChangeRequest)
class WorkerDayChangeRequestAdmin(admin.ModelAdmin):
    pass


@admin.register(ProductionMonth)
class ProductionMonthAdmin(admin.ModelAdmin):
    list_display = ('id', 'dt_first', 'total_days', 'norm_work_days', 'norm_work_hours')


@admin.register(AttendanceRecords)
class AttendanceRecordsAdmin(admin.ModelAdmin):
    list_display = ['id', 'dttm', 'type',]
    list_filter = ('type', 'verified', 'type')


@admin.register(ExchangeSettings)
class ExchangeSettingsAdmin(admin.ModelAdmin):
    pass


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    pass


@admin.register(OperationTemplate)
class OperationTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'operation_type')
    list_filter = ('operation_type', )
    search_fields = ('name',)


@admin.register(Employment)
class EmploymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'user')
    list_filter = ('shop', 'user')
    search_fields = ('user__first_name', 'user__last_name', 'shop__title', 'shop__parent__title')
