from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from src.db.models import (
    User,
    SuperShop,
    Shop,
    WorkerDay,
    PeriodDemand,
    PeriodDemandChangeLog,
    CashboxType,
    Cashbox,
    WorkerCashboxInfo,
    WorkerDayCashboxDetails,
    Notifications,
    WorkerPosition,
    Slot,
    UserWeekdaySlot,
    WorkerConstraint,
    WorkerDayChangeLog,
    Timetable,
)


@admin.register(User)
class QsUserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'super_shop_title', 'cashbox_type_name', 'position_title', 'id')
    search_fields = ('first_name', 'last_name', 'shop__super_shop__title', 'workercashboxinfo__cashbox_type__name', 'position__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def super_shop_title(instance: User):
        if instance.shop and instance.shop.super_shop:
            return instance.shop.super_shop.title
        return 'без магазина'

    @staticmethod
    def position_title(instance: User):
        return instance.position.title if instance.position else ''

    @staticmethod
    def cashbox_type_name(instance: User):
        cashboxinfo_set = instance.workercashboxinfo_set.all()
        return ' '.join(['"{}"'.format(cbi.cashbox_type.name) for cbi in cashboxinfo_set])


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


@admin.register(WorkerPosition)
class WorkerPositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'department_title', 'super_shop_title', 'id')
    search_fields = ('title', 'department__title', 'department__super_shop__title', 'id')
    list_filter = ('department', )

    @staticmethod
    def super_shop_title(instance: WorkerPosition):
        return instance.department.super_shop.title

    @staticmethod
    def department_title(instance: WorkerPosition):
        return instance.department.title


@admin.register(CashboxType)
class CashboxTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop_title', 'super_shop_title', 'dttm_added', 'do_forecast', 'id')
    search_fields = ('name', 'shop__title', 'shop__super_shop__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def shop_title(instance: CashboxType):
        return instance.shop.title

    @staticmethod
    def super_shop_title(instance: CashboxType):
        return instance.shop.super_shop.title


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ('name', 'cashbox_type_name', 'shop_title', 'super_shop_title', 'tm_start', 'tm_end', 'id')
    search_fields = ('name', 'shop__title', 'shop__super_shop__title', 'id')
    list_filter = ('shop', )

    @staticmethod
    def shop_title(instance: Slot):
        return instance.shop.title

    @staticmethod
    def super_shop_title(instance: Slot):
        return instance.shop.super_shop.title

    @staticmethod
    def cashbox_type_name(instance: Slot):
        if instance.cashbox_type:
            return instance.cashbox_type.name


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
    list_display = ('type_name', 'shop_title', 'super_shop_title', 'id')
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


@admin.register(PeriodDemand)
class PeriodDemandAdmin(admin.ModelAdmin):
    list_display = ('cashbox_type_name', 'shop_title', 'dttm_forecast', 'type', 'id')
    search_fields = ('cashbox_type__name', 'cashbox_type__shop__title', 'id')
    list_filter = ('cashbox_type__shop', )

    @staticmethod
    def cashbox_type_name(instance: PeriodDemand):
        return instance.cashbox_type.name

    @staticmethod
    def shop_title(instance: PeriodDemand):
        return instance.cashbox_type.shop.title


@admin.register(PeriodDemandChangeLog)
class PeriodDemandChangeLogAdmin(admin.ModelAdmin):
    list_display = ('cashbox_type_name', 'shop_title', 'dttm_from', 'dttm_to')
    search_fields = ('cashbox_type__name', 'cashbox_type__shop__title', 'id')
    list_filter = ('cashbox_type__shop', )

    @staticmethod
    def cashbox_type_name(instance: PeriodDemandChangeLog):
        return instance.cashbox_type.name

    @staticmethod
    def shop_title(instance: PeriodDemandChangeLog):
        return instance.cashbox_type.shop.title


@admin.register(WorkerCashboxInfo)
class WorkerCashboxInfoAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'cashbox_type_name', 'id')
    search_fields = ('worker__last_name', 'cashbox_type__name', 'id')
    list_filter = ('cashbox_type__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerCashboxInfo):
        return instance.worker.last_name

    @staticmethod
    def cashbox_type_name(instance: WorkerCashboxInfo):
        return instance.cashbox_type.name


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
    list_display = ('worker_last_name', 'shop_title', 'super_shop_title', 'dt', 'type', 'id')
    search_fields = ('worker__last_name', 'worker__shop__title', 'worker__shop__super_shop__title', 'id')
    list_filter = ('worker__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerConstraint):
        return instance.worker.last_name

    @staticmethod
    def shop_title(instance: WorkerDay):
        return instance.worker_shop.title

    @staticmethod
    def super_shop_title(instance: WorkerDay):
        return instance.worker_shop.super_shop.title


@admin.register(WorkerDayCashboxDetails)
class WorkerDayCashboxDetailsAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'super_shop_title', 'worker_day_dt', 'on_cashbox_type', 'id')
    search_fields = ('worker_day__worker__last_name', 'worker_day__worker__shop__title', 'id')
    list_filter = ('worker_day__worker__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerDayCashboxDetails):
        return instance.worker_day.worker.last_name

    @staticmethod
    def super_shop_title(instance: WorkerDayCashboxDetails):
        return instance.worker_day.worker_shop.title

    @staticmethod
    def worker_day_dt(instance: WorkerDayCashboxDetails):
        return instance.worker_day.dt

    @staticmethod
    def on_cashbox_type(instance: WorkerDayCashboxDetails):
        return instance.on_cashbox.type.name


@admin.register(WorkerDayChangeLog)
class WorkerDayChangeLogAdmin(admin.ModelAdmin):
    list_display = ('worker_last_name', 'super_shop_title', 'worker_day_dt', 'id')
    search_fields = ('worker_day__worker__last_name', 'worker_day__worker__shop__title', 'id')
    list_filter = ('worker_day__worker__shop',)

    @staticmethod
    def worker_last_name(instance: WorkerDayChangeLog):
        return instance.worker_day.worker.last_name

    @staticmethod
    def super_shop_title(instance: WorkerDayChangeLog):
        return instance.worker_day.worker_shop.title

    @staticmethod
    def worker_day_dt(instance: WorkerDayChangeLog):
        return instance.worker_day.dt


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
    list_display = ('shop_title', 'super_shop_title', 'dt', 'status', 'dttm_status_change', 'id')
    search_fields = ('shop__title', 'shop__super_shop__title')
    list_filter = ('shop',)

    @staticmethod
    def super_shop_title(instance: Timetable):
        return instance.shop.super_shop.title

    @staticmethod
    def shop_title(instance: Timetable):
        return instance.shop.title
