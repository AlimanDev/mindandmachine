from django.contrib import admin
from src.db.models import (
    User,
    SuperShop,
    Shop,
    WorkerDay,
    PeriodClients,
    PeriodQueues,
    PeriodProducts,
    PeriodDemandChangeLog,
    WorkType,
    Cashbox,
    WorkerCashboxInfo,
    WorkerDayCashboxDetails,
    Notifications,
    Slot,
    UserWeekdaySlot,
    WorkerConstraint,
    Timetable,
    ProductionDay,
    WorkerMonthStat,
    CameraCashboxStat,
    CameraCashbox,
    CameraClientGate,
    CameraClientEvent,
    OperationType,
    Group,
    FunctionGroup,
)


@admin.register(User)
class QsUserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'super_shop_title', 'work_type_name', 'id',)
    search_fields = ('first_name', 'last_name', 'shop__super_shop__title', 'workercashboxinfo__work_type__name', 'id')
    list_filter = ('shop', )

    @staticmethod
    def super_shop_title(instance: User):
        if instance.shop and instance.shop.super_shop:
            return instance.shop.super_shop.title
        return 'без магазина'

    @staticmethod
    def work_type_name(instance: User):
        cashboxinfo_set = instance.workercashboxinfo_set.all()
        return ' '.join(['"{}"'.format(cbi.work_type.name) for cbi in cashboxinfo_set])


@admin.register(SuperShop)
class SuperShopAdmin(admin.ModelAdmin):
    list_display = ('title', 'code', 'id')
    search_fields = list_display


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('title', 'super_shop_title', 'id')
    search_fields = ('title', 'super_shop__title', 'id')

    @staticmethod
    def super_shop_title(instance: Shop):
        return instance.super_shop.title


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop_title', 'super_shop_title', 'dttm_added', 'id')
    search_fields = ('name', 'shop__title', 'shop__super_shop__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def shop_title(instance: WorkType):
        return instance.shop.title

    @staticmethod
    def super_shop_title(instance: WorkType):
        return instance.shop.super_shop.title


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ('name', 'work_type_name', 'shop_title', 'super_shop_title', 'tm_start', 'tm_end', 'id')
    search_fields = ('name', 'shop__title', 'shop__super_shop__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def shop_title(instance: Slot):
        return instance.shop.title

    @staticmethod
    def super_shop_title(instance: Slot):
        return instance.shop.super_shop.title

    @staticmethod
    def work_type_name(instance: Slot):
        if instance.work_type:
            return instance.work_type.name


@admin.register(UserWeekdaySlot)
class UserWeekDaySlotAdmin(admin.ModelAdmin):
    list_display = ('worker_first_name', 'worker_last_name', 'shop_title', 'super_shop_title', 'slot_name',
                    'weekday', 'id')
    search_fields = ('worker__first_name','worker__last_name', 'worker__shop__title', 'worker__shop__super_shop__title',
                     'slot__name', 'id')
    list_filter = ('worker__shop', )

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
    def super_shop_title(instance: UserWeekdaySlot):
        return instance.worker.shop.super_shop.title


@admin.register(Cashbox)
class CashboxAdmin(admin.ModelAdmin):
    list_display = ('type_name', 'shop_title', 'super_shop_title', 'id', 'number')
    search_fields = ('type__name', 'type__shop__title', 'type__shop__super_shop__title', 'id')
    list_filter = ('type__shop', )

    @staticmethod
    def type_name(instance: Cashbox):
        return instance.type.name

    @staticmethod
    def shop_title(instance: Cashbox):
        return instance.type.shop.title

    @staticmethod
    def super_shop_title(instance: Cashbox):
        return instance.type.shop.super_shop.title


@admin.register(PeriodClients)
class PeriodClientsAdmin(admin.ModelAdmin):
    list_display = ('work_type_name', 'shop_title', 'value', 'dttm_forecast', 'type', 'id')
    search_fields = ('operation_type__work_type__name', 'operation_type__work_type__shop__title', 'id')
    list_filter = ('type', 'operation_type__work_type')

    @staticmethod
    def work_type_name(instance: PeriodClients):
        return instance.operation_type.work_type.name

    @staticmethod
    def shop_title(instance: PeriodClients):
        return instance.operation_type.work_type.shop.title


@admin.register(PeriodQueues)
class PeriodQueuesAdmin(admin.ModelAdmin):
    list_display = ('work_type_name', 'shop_title', 'value', 'dttm_forecast', 'type', 'id')
    search_fields = ('operation_type__work_type__name', 'operation_type__work_type__shop__title', 'id')
    list_filter = ('operation_type__work_type', 'type')

    @staticmethod
    def work_type_name(instance: PeriodQueues):
        return instance.operation_type.work_type.name

    @staticmethod
    def shop_title(instance: PeriodQueues):
        return instance.operation_type.work_type.shop.title


@admin.register(PeriodProducts)
class PeriodProductsAdmin(admin.ModelAdmin):
    list_display = ('work_type_name', 'shop_title', 'value', 'dttm_forecast', 'type', 'id')
    search_fields = ('operation_type__work_type__name', 'operation_type__work_type__shop__title', 'id')
    list_filter = ('operation_type__work_type', 'type')

    @staticmethod
    def work_type_name(instance: PeriodProducts):
        return instance.operation_type.work_type.name

    @staticmethod
    def shop_title(instance: PeriodProducts):
        return instance.operation_type.work_type.shop.title


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
    list_filter = ('worker__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerConstraint):
        return instance.worker.last_name


@admin.register(WorkerDay)
class WorkerDayAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'shop_title', 'super_shop_title', 'dt', 'type', 'id', 'dttm_work_start',
                    'dttm_work_end')
    search_fields = ('worker__last_name', 'worker__shop__title', 'worker__shop__super_shop__title', 'id', 'dt')
    list_filter = ('worker__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerConstraint):
        return instance.worker.last_name

    @staticmethod
    def shop_title(instance: WorkerDay):
        return instance.worker.shop.title

    @staticmethod
    def super_shop_title(instance: WorkerDay):
        return instance.worker.shop.super_shop.title


@admin.register(WorkerDayCashboxDetails)
class WorkerDayCashboxDetailsAdmin(admin.ModelAdmin):
    # todo: нет нормального отображения для конкретного pk(скорее всего из-за harakiri time в настройках uwsgi)
    # todo: upd: сервак просто падает если туда зайти
    list_display = ('worker_last_name', 'shop_title', 'worker_day_dt', 'on_work_type', 'id', 'dttm_from', 'dttm_to')
    search_fields = ('worker_day__worker__last_name', 'worker_day__worker__shop__title', 'id')
    list_filter = ('worker_day__worker__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerDayCashboxDetails):
        return instance.worker_day.worker.last_name

    @staticmethod
    def shop_title(instance: WorkerDayCashboxDetails):
        return instance.worker_day.worker.shop.title

    @staticmethod
    def worker_day_dt(instance: WorkerDayCashboxDetails):
        return instance.worker_day.dt

    @staticmethod
    def on_work_type(instance: WorkerDayCashboxDetails):
        return instance.work_type.name if instance.work_type else ''


@admin.register(Notifications)
class NotificationsAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'shop_title', 'super_shop_title', 'dttm_added', 'id')
    search_fields = ('to_worker__last_name', 'to_worker__shop__title', 'to_worker__shop__super_shop__title', 'id')
    list_filter = ('to_worker__shop',)

    @staticmethod
    def worker_last_name(instance: Notifications):
        return instance.to_worker.last_name

    @staticmethod
    def super_shop_title(instance: Notifications):
        return instance.to_worker.shop.super_shop.title

    @staticmethod
    def shop_title(instance: Notifications):
        return instance.to_worker.shop.title


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop_title', 'super_shop_title', 'dt', 'status', 'dttm_status_change',
                    'fot', 'idle', 'lack', 'workers_amount', 'revenue', 'fot_revenue',)
    search_fields = ('shop__title', 'shop__super_shop__title')
    list_filter = ('shop',)

    @staticmethod
    def super_shop_title(instance: Timetable):
        return instance.shop.super_shop.title

    @staticmethod
    def shop_title(instance: Timetable):
        return instance.shop.title


@admin.register(ProductionDay)
class ProductionDayAdmin(admin.ModelAdmin):
    list_display = ('dt', 'type')


@admin.register(WorkerMonthStat)
class WorkerMonthStatAdmin(admin.ModelAdmin):
    list_display = ('worker_id', 'month')


@admin.register(CameraCashboxStat)
class CameraCashboxStatAdmin(admin.ModelAdmin):
    list_display = ('camera_cashbox', 'dttm', 'queue')


@admin.register(CameraCashbox)
class CameraCashboxStatAdmin(admin.ModelAdmin):
    list_display = ('name', 'cashbox')


@admin.register(CameraClientGate)
class CameraClientGateAdmin(admin.ModelAdmin):
    list_display = ('name', 'type')


@admin.register(CameraClientEvent)
class CameraClientEventAdmin(admin.ModelAdmin):
    list_display = ('dttm', 'gate', 'type')
    list_filter = ('gate', 'type')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_dispaly = ('id', 'dttm_added', 'name', 'subordinates')
    list_filter = ('id', 'name')


@admin.register(FunctionGroup)
class FunctionGroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'access_type', 'group', 'func')
    list_filter = ('access_type', 'group', 'func')
    search_fields = ('id',)


@admin.register(OperationType)
class OperationTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'work_type_name', 'speed_coef', 'do_forecast')
    list_filter = ('do_forecast', 'work_type__shop__title')

    @staticmethod
    def work_type_name(instance: OperationType):
        return instance.work_type.name
