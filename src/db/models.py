from django.db import models
from django.contrib.auth.models import AbstractUser as DjangoAbstractUser
from . import utils


class Shop(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    title = models.CharField(max_length=64, unique=True)

    mean_queue_length = models.FloatField(default=3)
    max_queue_length = models.FloatField(default=7)
    plain_part = models.FloatField(default=0.1)

    beta = models.FloatField(default=0.9)  # for creating timetable, (a function from previous 3 variables)

    demand_coef = models.FloatField(default=1)  # unknown trend for algorithm


class User(DjangoAbstractUser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class WorkType(utils.Enum):
        TYPE_INTERNAL = 0
        TYPE_5_2 = 1
        TYPE_2_2 = 2
        TYPE_HOUR = 3
        TYPE_SOS = 4
        TYPE_MANAGER = 5

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    dt_hired = models.DateField(null=True, blank=True)
    dt_fired = models.DateField(null=True, blank=True)

    birthday = models.DateField(null=True, blank=True)
    avatar = models.ImageField(null=True, blank=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    work_type = utils.EnumField(WorkType)
    permissions = models.BigIntegerField()


class CashboxType(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    name = models.CharField(max_length=128)


class Cashbox(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
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


class PeriodDemandChangeLog(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_changed = models.DateTimeField(auto_now_add=True)
    period_demand = models.ForeignKey(PeriodDemand, on_delete=models.PROTECT)
    from_amount = models.PositiveIntegerField()
    to_amount = models.PositiveIntegerField()
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)


class WorkerCashboxInfo(models.Model):
    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)
    mean_speed = models.FloatField()
    bills_amount = models.PositiveIntegerField()

    period = models.PositiveIntegerField(default=90)  # show for how long in days the data was collect
    dt_period_end = models.DateField()


class WorkerConstraint(models.Model):
    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    weekday = models.PositiveSmallIntegerField()
    tm = models.TimeField()
    is_active = models.BooleanField(default=False)


class WorkerDay(models.Model):
    class Meta(object):
        unique_together = (('worker', 'dt'),)

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
    worker = models.ForeignKey(User, on_delete=models.PROTECT)  # todo: make immutable
    dt = models.DateField()  # todo: make immutable
    type = utils.EnumField(Type)

    tm_work_start = models.TimeField(null=True, blank=True)
    tm_work_end = models.TimeField(null=True, blank=True)
    tm_break_start = models.TimeField(null=True, blank=True)

    is_manual_tuning = models.BooleanField(default=False)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'Worker {} | Date {} | {}'.format(self.id, self.dt, self.Type.get_name_by_value(self.type))


class WorkerDayCashboxDetails(models.Model):
    id = models.BigAutoField(primary_key=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)
    on_cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT)

    tm_from = models.TimeField()
    tm_to = models.TimeField()


class WorkerDayChangeRequest(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)

    # extra fields for SQL SELECT performance
    worker_day_dt = models.DateField()
    worker_day_worker = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')

    type = utils.EnumField(WorkerDay.Type)

    tm_work_start = models.TimeField(null=True, blank=True)
    tm_work_end = models.TimeField(null=True, blank=True)
    tm_break_start = models.TimeField(null=True, blank=True)


class WorkerDayChangeLog(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_changed = models.DateTimeField(auto_now_add=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)

    # extra fields for SQL SELECT performance
    worker_day_dt = models.DateField()
    worker_day_worker = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')

    from_type = utils.EnumField(WorkerDay.Type)
    from_tm_work_start = models.TimeField(null=True, blank=True)
    from_tm_work_end = models.TimeField(null=True, blank=True)
    from_tm_break_start = models.TimeField(null=True, blank=True)

    to_type = utils.EnumField(WorkerDay.Type)
    to_tm_work_start = models.TimeField(null=True, blank=True)
    to_tm_work_end = models.TimeField(null=True, blank=True)
    to_tm_break_start = models.TimeField(null=True, blank=True)

    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)


class Notifications(models.Model):
    class Type(utils.Enum):
        SYSTEM_NOTICE = 1
        CHANGE_REQUEST_NOTICE = 2
        CHANGE_TIMETABLE_NOTICE = 3
        CHANGE_WORKER_INFO = 4

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    to_worker = models.ForeignKey(User, on_delete=models.PROTECT)

    text = models.CharField(max_length=512)
    type = utils.EnumField(Type)

    worker_day_change_request = models.ForeignKey(WorkerDayChangeRequest, on_delete=models.PROTECT, null=True, blank=True)
    worker_day_change_log = models.ForeignKey(WorkerDayChangeLog, on_delete=models.PROTECT, null=True, blank=True)
    period_demand_log = models.ForeignKey(PeriodDemandChangeLog, on_delete=models.PROTECT, null=True, blank=True)

    shown = models.BooleanField(default=False)


class OfficialHolidays(models.Model):
    id = models.BigAutoField(primary_key=True)

    country = models.CharField(max_length=4)
    date = models.DateField()
