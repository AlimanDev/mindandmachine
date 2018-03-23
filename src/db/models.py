from django.db import models
from django.contrib.auth.models import User as DjangoUser
from . import utils


class Shop(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    title = models.CharField(max_length=64, unique=True)


class Worker(models.Model):
    class Type(utils.Enum):
        TYPE_5_2 = 1
        TYPE_2_2 = 2
        TYPE_HOUR = 3
        TYPE_SOS = 4
        TYPE_MANAGER = 5

    id = models.BigAutoField(primary_key=True)
    django_user = models.OneToOneField(DjangoUser, on_delete=models.PROTECT)

    dttm_added = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    birthday = models.DateField(null=True, blank=True)
    avatar = models.ImageField(null=True, blank=True)

    shop_id = models.ForeignKey(Shop, on_delete=models.PROTECT)
    work_type = utils.EnumField(Type)
    permissions = models.BigIntegerField()


class SettingsModel(models.Model):
    id = models.BigAutoField(primary_key=True)

    shop_id = models.OneToOneField(Shop, on_delete=models.PROTECT)

    mean_queue_length = models.FloatField(default=3)
    max_queue_length = models.FloatField(default=7)
    plain_part = models.FloatField(default=0.1)

    beta = models.FloatField(default=0.9)  # for creating timetable, (a function from previous 3 variables)

    demand_coef = models.FloatField(default=1)  # unknown trend for algorithm


class CashboxType(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    dttm_deleted = models.DateTimeField(null=True, blank=True)
    shop_id = models.ForeignKey(Shop, on_delete=models.PROTECT)
    name = models.CharField(max_length=128)


class Cashbox(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)
    number = models.CharField(max_length=6)
    bio = models.CharField(max_length=512, default='')


class PeriodDemand(models.Model):
    class Type(utils.Enum):
        LONG_FORECAST = 1
        SHORT_FORECAST = 2
        FACT = 3

    id = models.BigAutoField(primary_key=True)

    dttm_forecast = models.DateTimeField()
    clients = models.PositiveIntegerField()
    products = models.PositiveIntegerField()

    type = utils.EnumField(Type)
    сashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)

    queue_wait_time = models.FloatField()  # in minutes
    queue_wait_length = models.FloatField()


class PeriodDemandLog(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_changed = models.DateTimeField(auto_now_add=True)
    period_demand = models.ForeignKey(PeriodDemand, on_delete=models.PROTECT)
    from_amount = models.PositiveIntegerField()
    to_amount = models.PositiveIntegerField()
    changed_by = models.ForeignKey(Worker, on_delete=models.PROTECT)


class WorkerCashInfo(models.Model):
    id = models.BigAutoField(primary_key=True)

    # for the last 3 month
    type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)
    mean_speed = models.FloatField()
    bills_amount = models.PositiveIntegerField()
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)

    is_all_period = models.BooleanField()  # show if data about cashier exist for period more or equal then 3 month


class WorkerConstraint(models.Model):
    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    weekday = models.PositiveSmallIntegerField()
    tm = utils.DayTimeField()
    is_active = models.BooleanField(default=False)


class WorkerDay(models.Model):
    class Type(utils.Enum):
        TYPE_HOLIDAY = 1
        TYPE_WORKDAY = 2
        TYPE_VACATION = 3
        TYPE_SICK = 4
        TYPE_QUALIFICATION = 5
        TYPE_ABSENSE = 6
        TYPE_MATERNITY = 7

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dt = models.DateField()
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    type = utils.EnumField(Type)

    tm_work_start = utils.DayTimeField(null=True, blank=True)
    tm_work_end = utils.DayTimeField(null=True, blank=True)
    tm_break_start = utils.DayTimeField(null=True, blank=True)

    is_manual_tuning = models.BooleanField(default=False)


class WorkerDayCashboxDetails(models.Model):
    id = models.BigAutoField(primary_key=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)
    on_cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT)

    tm_from = utils.DayTimeField()
    tm_to = utils.DayTimeField()


class WorkerChangeRequest(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)

    type = utils.EnumField(WorkerDay.Type)

    tm_work_start = utils.DayTimeField(null=True, blank=True)
    tm_work_end = utils.DayTimeField(null=True, blank=True)
    tm_break_start = utils.DayTimeField(null=True, blank=True)


class WorkerDayLog(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_changed = models.DateTimeField(auto_now_add=True)
    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)

    from_type = utils.EnumField(WorkerDay.Type)
    to_type = utils.EnumField(WorkerDay.Type)

    from_tm_work_start = utils.DayTimeField(null=True, blank=True)
    to_tm_work_start = utils.DayTimeField(null=True, blank=True)

    from_tm_work_end = utils.DayTimeField(null=True, blank=True)
    to_tm_work_end = utils.DayTimeField(null=True, blank=True)

    changed_by = models.ForeignKey(Worker, on_delete=models.PROTECT)


class Notifications(models.Model):
    class Type(utils.Enum):
        SYSTEM_NOTICE = 1
        CHANGE_REQUEST_NOTICE = 2
        CHANGE_TIMETABLE_NOTICE = 3
        CHANGE_WORKER_INFO = 4

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    to_worker = models.ForeignKey(Worker, on_delete=models.PROTECT)

    text = models.CharField(max_length=512)
    type = utils.EnumField(Type)

    worker_change_request = models.ForeignKey(WorkerChangeRequest, on_delete=models.PROTECT, null=True, blank=True)
    worker_day_log = models.ForeignKey(WorkerDayLog, on_delete=models.PROTECT, null=True, blank=True)
    period_demand_log = models.ForeignKey(PeriodDemandLog, on_delete=models.PROTECT, null=True, blank=True)

    shown = models.BooleanField(default=False)
