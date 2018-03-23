from django.db import models


class SettingsModel(models.Model):
    # for safety, that only 1 model could exist
    unique_field = models.CharField(max_length=1, choices=('u', 'unique'), unique=True)

    mean_queue_length = models.FloatField(default=3)
    max_queue_length = models.FloatField(default=7)
    plain_part = models.FloatField(default=0.1)

    beta = models.FloatField(default=0.9)  # for creating timetable, (a function from previous 3 variables)

    demand_coef = models.FloatField(default=1)  # unknown trend for algorithm


class CashboxType(models.Model):
    name = models.CharField(max_length=128)
    dttm_added = models.DateTimeField(auto_now_add=True)

    deleted = models.BooleanField(default=False)  # is it really needed?
    dttm_deleted = models.DateTimeField(null=True, blank=True)


class Cashbox(models.Model):
    dttm_added = models.DateTimeField(auto_now_add=True)

    type = models.ForeignKey(CashboxType)
    number = models.CharField(max_length=6)
    bio = models.CharField(max_length=512, default='')

    deleted = models.BooleanField(default=False)  # is it really needed?
    dttm_deleted = models.DateTimeField(null=True, blank=True)


class PeriodDemand(models.Model):
    LONG_FORECAST = 'LF'
    SHORT_FORECAST = 'SF'
    FACT = 'F'
    TYPE = (
        (LONG_FORECAST, 'Long forecast'),
        (SHORT_FORECAST, 'Short forecast'),
        (FACT, 'fact'),
    )

    dttm_forecast = models.DateTimeField()
    clients = models.PositiveIntegerField()
    products = models.PositiveIntegerField()

    type = models.CharField(max_length=2, choices=TYPE)
    сashbox_type = models.ForeignKey(CashboxType)

    queue_wait_time = models.FloatField()  # in minutes
    queue_wait_length = models.FloatField()


class PeriodDemandLog(models.Model):
    dttm_changed = models.DateTimeField(auto_now_add=True)
    period_demand = models.ForeignKey(PeriodDemand)
    from_amount = models.PositiveIntegerField()
    to_amount = models.PositiveIntegerField()
    changed_by = models.ForeignKey(Worker)


# class PeriodQueue(models.Model):
#     dttm_forecast = models.DateTimeField() # maybe should have foreign key to period demand?
#     wait_time = models.FloatField() # in minutes
#     wait_length = models.FloatField()


class UserGroup(models.Model):
    group_name = models.CharField(max_length=64)


class Worker(models.Model):  # User
    SCHEDULE5_2 = '52'
    SCHEDULE2_2 = '22'
    SCHEDULE_HOUR = 'H'
    SCHEDULE_SOS = 'SS'
    MANAGER = 'M'

    SCHEDULE_TYPES = (
        (SCHEDULE5_2, 'work schedule 5/2'),
        (SCHEDULE2_2, 'work schedule 2/2'),
        (SCHEDULE_HOUR, 'working hours'),
        (SCHEDULE_SOS, 'sos group (pair hours)'),
        (MANAGER, 'manager'),
    )

    dttm_added = models.DateTimeField(auto_now_add=True)

    avatar = models.ImageField(null=True, blank=True)
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    birthday = models.DateField(null=True, blank=True)

    work_type = models.CharField(max_length=2, choices=SCHEDULE_TYPES)

    permissions = models.ManyToManyField(UserGroup)

    deleted = models.BooleanField(default=False)
    dt_deleted = models.DateField(null=True, blank=True)


class WorkerCashInfo(models.Model):
    # for the last 3 month
    type = models.ForeignKey(CashboxType)
    mean_speed = models.FloatField()
    bills_amount = models.PositiveIntegerField()
    worker = models.ForeignKey(Worker)

    is_all_period = models.BooleanField() # show if data about cashier exist for period more or equal then 3 month


class WorkerConstraint(models.Model):

    worker = models.ForeignKey(Worker)
    weekday = models.PositiveSmallIntegerField()
    tm = models.PositiveIntegerField() # time format hhmm, for example : 745 (7:45), 2300 (23:00)
    is_active = models.BooleanField(default=False)

    # is_strict = models.BooleanField(default=True) # constraints maybe strict or not

    # to?do: add opportunity to create constraint to future


class WorkerDay(models.Model):
    TYPE_HOLIDAY = 'H'
    TYPE_WORKDAY = 'W'
    TYPE_VACATION = 'V'
    TYPE_SICK = 'S'
    TYPE_QUALIFICATION = 'Q'
    TYPE_ABSENSE = 'A'
    TYPE_MATERNITY = 'M'
    DAY_TYPES = (
        (TYPE_HOLIDAY, 'holiday (day off)'),
        (TYPE_WORKDAY, 'workday'),
        (TYPE_VACATION, 'holidays / vacation'),
        (TYPE_SICK, 'sick day'),
        (TYPE_QUALIFICATION, 'raising qualification'),
        (TYPE_ABSENSE, 'absensed'),
        (TYPE_MATERNITY, 'on maternity leave'),
    )

    dttm_added = models.DateTimeField(auto_now_add=True)
    dt = models.DateField()
    type = models.CharField(max_length=1, choices=DAY_TYPES)
    worker = models.ForeignKey(Worker)

    tm_start_work = models.PositiveIntegerField(null=True, blank=True)  # time format hhmm, for example : 745 (7:45), 2300 (23:00)
    tm_end_work = models.PositiveIntegerField(null=True, blank=True)  # for hour work day
    tm_break = models.PositiveIntegerField(null=True, blank=True)

    is_manual_tuning = models.BooleanField(default=False) # that algorithm understand that it is constraints


class WorkerDayCashboxDetails(models.Model):
    worker_day = models.ForeignKey(WorkerDay)
    on_cashbox = models.ForeignKey(Cashbox)

    from_tm = models.PositiveIntegerField()
    to_tm = models.PositiveIntegerField()


class WorkerChangeRequest(models.Model):
    dttm_added = models.DateTimeField(auto_now_add=True)
    worker_day = models.ForeignKey(WorkerDay)

    type = models.CharField(max_length=1, choices=WorkerDay.DAY_TYPES)

    tm_start_work = models.PositiveIntegerField(null=True, blank=True)  # time format hhmm, for example : 745 (7:45), 2300 (23:00)
    tm_end_work = models.PositiveIntegerField(null=True, blank=True)  # for hour work day
    tm_break = models.PositiveIntegerField(null=True, blank=True)


class WorkerDayLog(models.Model):
    dttm_changed = models.DateTimeField(auto_now_add=True)
    worker_day = models.ForeignKey(WorkerDay)

    from_type = models.CharField(max_length=1, choices=WorkerDay.DAY_TYPES)
    to_type = models.CharField(max_length=1, choices=WorkerDay.DAY_TYPES)

    from_tm_start_work = models.PositiveIntegerField(null=True, blank=True)
    to_tm_start_work = models.PositiveIntegerField(null=True, blank=True)

    changed_by = models.ForeignKey(Worker)


class Notifications(models.Model):
    SYSTEM_NOTICE = 'SYS'
    CHANGE_REQUEST_NOTICE = 'REQ'
    CHANGE_TIMETABLE_NOTICE = 'CTT'
    CHANGE_WORKER_INFO = 'WI'

    TYPES = (
        (SYSTEM_NOTICE, 'system notice'),
        (CHANGE_REQUEST_NOTICE, 'request for change timetable'),
        (CHANGE_TIMETABLE_NOTICE, 'manual change'),
        (CHANGE_WORKER_INFO, 'change worker information'),
    )

    # dttm_added = models.DateTimeField(auto_now_add=True)
    to_worker = models.ForeignKey(Worker)

    text = models.CharField(max_length=512)  # 512 - bytes or symbols? must be symbols
    type = models.CharField(max_length=3, choices=TYPES)  # actually duplicating info

    worker_change_request = models.ForeignKey(WorkerChangeRequest, null=True, blank=True)
    worker_day_log = models.ForeignKey(WorkerDayLog, null=True, blank=True)
    period_demand_log = models.ForeignKey(PeriodDemandLog, null=True, blank=True)

    shown = models.BooleanField(default=False)

