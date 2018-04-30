from django.db import models
from django.contrib.auth.models import AbstractUser as DjangoAbstractUser
from . import utils


# магазин
class SuperShop(models.Model):
    id = models.BigAutoField(primary_key=True)

    title = models.CharField(max_length=64, unique=True)
    hidden_title = models.CharField(max_length=64, unique=True)

    code = models.CharField(max_length=64, null=True, blank=True)

    dt_opened = models.DateField(null=True, blank=True)
    dt_closed = models.DateField(null=True, blank=True)


# на самом деле это отдел
class Shop(models.Model):
    class Meta(object):
        unique_together = (('super_shop', 'title'), ('super_shop', 'hidden_title'),)

    id = models.BigAutoField(primary_key=True)

    super_shop = models.ForeignKey(SuperShop, on_delete=models.PROTECT)
    full_interface = models.BooleanField(default=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    title = models.CharField(max_length=64)
    hidden_title = models.CharField(max_length=64)

    mean_queue_length = models.FloatField(default=3)
    max_queue_length = models.FloatField(default=7)
    dead_time_part = models.FloatField(default=0.1)

    beta = models.FloatField(default=0.9)  # for creating timetable, (a function from previous 3 variables)

    demand_coef = models.FloatField(default=1)  # unknown trend for algorithm


class User(DjangoAbstractUser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class WorkType(utils.Enum):
        TYPE_5_2 = 1
        TYPE_2_2 = 2
        TYPE_HOUR = 3
        TYPE_SOS = 4
        TYPE_MANAGER = 5
        # TYPE_3_3 = 6
        # TYPE_DISABLED = 7
        # TYPE_PREGNANT = 8

    id = models.BigAutoField(primary_key=True)

    shop = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT)  # todo: make immutable
    work_type = utils.EnumField(WorkType, null=True, blank=True)
    permissions = models.BigIntegerField(default=0)

    middle_name = models.CharField(max_length=64, blank=True, null=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    dt_hired = models.DateField(null=True, blank=True)
    dt_fired = models.DateField(null=True, blank=True)

    birthday = models.DateField(null=True, blank=True)
    avatar = models.ImageField(null=True, blank=True, upload_to='user_avatar/%Y/%m')

    comment = models.CharField(max_length=2048, default='')
    extra_info = models.CharField(max_length=512, default='')

    auto_timetable = models.BooleanField(default=True)


class CashboxType(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    name = models.CharField(max_length=128)
    speed_coef = models.FloatField(default=1)
    is_stable = models.BooleanField(default=True)


class Cashbox(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)
    number = models.CharField(max_length=6)
    bio = models.CharField(max_length=512, default='')


class PeriodDemand(models.Model):
    class Type(utils.Enum):
        LONG_FORECAST = 1  # 60 day
        SHORT_FORECAST = 2  # 10 day
        FACT = 3  # real

    id = models.BigAutoField(primary_key=True)

    dttm_forecast = models.DateTimeField()
    clients = models.FloatField()
    products = models.FloatField()

    type = utils.EnumField(Type)
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)

    queue_wait_time = models.FloatField()  # in minutes
    queue_wait_length = models.FloatField()


class PeriodDemandChangeLog(models.Model):
    id = models.BigAutoField(primary_key=True)

    dttm_from = models.DateTimeField()
    dttm_to = models.DateTimeField()
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)
    multiply_coef = models.FloatField(null=True, blank=True)
    set_value = models.FloatField(null=True, blank=True)


class WorkerCashboxInfo(models.Model):
    class Meta(object):
        unique_together = (('worker', 'cashbox_type'),)

    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)

    is_active = models.BooleanField(default=True)

    period = models.PositiveIntegerField(default=90)  # show for how long in days the data was collect

    mean_speed = models.FloatField(default=1)
    bills_amount = models.PositiveIntegerField(default=0)


class WorkerConstraint(models.Model):
    class Meta(object):
        unique_together = (('worker', 'weekday', 'tm'),)

    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday
    tm = models.TimeField()


class WorkerDay(models.Model):
    class Meta(object):
        unique_together = (('worker', 'worker_shop', 'dt'),)

    class Type(utils.Enum):
        TYPE_HOLIDAY = 1
        TYPE_WORKDAY = 2
        TYPE_VACATION = 3
        TYPE_SICK = 4
        TYPE_QUALIFICATION = 5
        TYPE_ABSENSE = 6
        TYPE_MATERNITY = 7
        TYPE_BUSINESS_TRIP = 8
        TYPE_ETC = 9

        TYPE_DELETED = 10

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    worker = models.ForeignKey(User, on_delete=models.PROTECT)  # todo: make immutable
    dt = models.DateField()  # todo: make immutable
    type = utils.EnumField(Type)

    # extra field for SQL select
    worker_shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='+')

    tm_work_start = models.TimeField(null=True, blank=True)
    tm_work_end = models.TimeField(null=True, blank=True)
    tm_break_start = models.TimeField(null=True, blank=True)

    is_manual_tuning = models.BooleanField(default=False)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'Worker {} | Date {} | {}'.format(self.id, self.dt, self.Type.get_name_by_value(self.type))

    def is_type_with_tm_range(self, t):
        return t in (self.Type.TYPE_WORKDAY.value, self.Type.TYPE_BUSINESS_TRIP.value, self.Type.TYPE_QUALIFICATION.value)


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
    comment = models.CharField(max_length=128, default='')


class Notifications(models.Model):
    class Type(utils.Enum):
        SYSTEM_NOTICE = 1
        CHANGE_REQUEST_NOTICE = 2
        CHANGE_TIMETABLE_NOTICE = 3
        CHANGE_WORKER_INFO = 4

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    to_worker = models.ForeignKey(User, on_delete=models.PROTECT)

    was_read = models.BooleanField(default=False)

    text = models.CharField(max_length=512)
    type = utils.EnumField(Type)

    worker_day_change_request = models.ForeignKey(WorkerDayChangeRequest, on_delete=models.PROTECT, null=True, blank=True)
    worker_day_change_log = models.ForeignKey(WorkerDayChangeLog, on_delete=models.PROTECT, null=True, blank=True)
    period_demand_log = models.ForeignKey(PeriodDemandChangeLog, on_delete=models.PROTECT, null=True, blank=True)


class OfficialHolidays(models.Model):
    id = models.BigAutoField(primary_key=True)

    country = models.CharField(max_length=4)
    date = models.DateField()


class LevelType(models.Model):
    class Type(utils.Enum):
        LOW = 1
        MIDDLE = 2
        HIGH = 3

    id = models.BigAutoField(primary_key=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    type = utils.EnumField(Type)
    weekday = models.PositiveSmallIntegerField()
    tm_from = models.TimeField()
    tm_to = models.TimeField()


class WaitTimeInfo(models.Model):
    id = models.BigAutoField(primary_key=True)

    dt = models.DateField()
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)
    wait_time = models.PositiveIntegerField()
    proportion = models.FloatField()
    type = utils.EnumField(PeriodDemand.Type)


class Timetable(models.Model):
    class Meta(object):
        unique_together = (('shop', 'dt'),)

    class Status(utils.Enum):
        READY = 1
        PROCESSING = 2
        ERROR = 3

    id = models.BigAutoField(primary_key=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    dt = models.DateField()
    status = utils.EnumField(Status)
    dttm_status_change = models.DateTimeField()
