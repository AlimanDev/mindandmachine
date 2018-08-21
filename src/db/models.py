from django.db import models
from django.contrib.auth.models import (
    AbstractUser as DjangoAbstractUser,
    UserManager
)
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from . import utils
import datetime

# __all__ = [
#     'SuperShop',
#     'Shop',
#     'WorkerPosition',
#     'User',
#     'CashboxType',
#     'UserWeekdaySlot',
#     'Slot',
#     'Cashbox',
#     'PeriodDemand',
#     'PeriodDemandChangeLog',
#     'WorkerCashboxInfo',
#     'WorkerConstraint',
#     'WorkerDay',
#     'WorkerDayCashboxDetails',
#     'WorkerDayChangeRequest',
#     'WorkerDayChangeLog',
#     'Notifications',
#     'OfficialHolidays',
#     'LevelType',
#     'WaitTimeInfo',
#     'Timetable',
# ]


# магазин
class SuperShop(models.Model):
    class Meta:
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'

    id = models.BigAutoField(primary_key=True)

    title = models.CharField(max_length=64, unique=True)
    hidden_title = models.CharField(max_length=64, unique=True)

    code = models.CharField(max_length=64, null=True, blank=True)

    dt_opened = models.DateField(null=True, blank=True)
    dt_closed = models.DateField(null=True, blank=True)

    tm_start = models.TimeField(null=True, blank=True, default=datetime.time(hour=7))
    tm_end = models.TimeField(null=True, blank=True, default=datetime.time(hour=23, minute=59, second=59))

    def __str__(self):
        return '{}, {}, {}'.format(self.title, self.code, self.id)
        # return f'{self.title}, {self.code}, {self.id}'


# на самом деле это отдел
class Shop(models.Model):
    class Meta(object):
        unique_together = (('super_shop', 'title'), ('super_shop', 'hidden_title'),)
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'

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

    forecast_step_minutes = models.TimeField(default=datetime.time(minute=15))
    # man_presence = models.FloatField(default=0)

    count_lack = models.BooleanField(default=False)

    # json fields
    method_params  = models.CharField(max_length=4096, default='[]')
    cost_weights   = models.CharField(max_length=4096, default='{}')
    init_params    = models.CharField(max_length=2048, default='{"n_working_days_optimal": 20}')
    break_triplets = models.CharField(max_length=1024, default='[]')

    def __str__(self):
        return '{}, {}, {}'.format(self.title, self.super_shop.title, self.id)
        # return f'{self.title}, {self.super_shop.title}, {self.id}'


class WorkerPosition(models.Model):
    """
    Describe employee's department and position
    """

    class Meta:
        verbose_name = 'Должность сотрудника'
        verbose_name_plural = 'Должности сотрудников'

    id = models.BigAutoField(primary_key=True)

    department = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=64)

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.title, self.department.title, self.department.super_shop.title, self.id)
        # return f'{self.title}, {self.department.title}, {# self.department.super_shop.title}, {self.id}'


class WorkerManager(UserManager):
    def qos_filter_active(self, dt_from, dt_to, *args, **kwargs):
        """
        hired earlier then dt_from, hired later then dt_to
        :param dt_from:
        :param dt_to:
        :param args:
        :param kwargs:
        :return:
        """

        return self.filter(
            models.Q(dt_hired__lte=dt_from) | models.Q(dt_hired__isnull=True)
        ).filter(
            models.Q(dt_fired__gte=dt_to) | models.Q(dt_fired__isnull=True)
        ).filter(*args, **kwargs)


class User(DjangoAbstractUser):

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        if self.shop and self.shop.super_shop:
            ss_title = self.shop.super_shop.title
        else:
            ss_title = None
        return '{}, {}, {}, {}'.format(self.first_name, self.last_name, ss_title, self.id)
        # return f'{self.first_name}, {self.last_name}, {ss_title}, {self.id}'

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

    GROUP_CASHIER = 'C'
    GROUP_MANAGER = 'M'
    GROUP_SUPERVISOR = 'S'
    GROUP_DIRECTOR = 'D'
    GROUP_HQ = 'H'

    GROUP_TYPE = (
        (GROUP_CASHIER, 'cashiers'),
        (GROUP_MANAGER, 'manager'),
        (GROUP_SUPERVISOR, 'supervisor'),
        (GROUP_DIRECTOR, 'director'),
        (GROUP_HQ, 'headquarter')
    )

    __all_groups__ = [x[0] for x in GROUP_TYPE]
    __except_cashiers__ = [GROUP_MANAGER, GROUP_SUPERVISOR, GROUP_DIRECTOR, GROUP_HQ]
    __allowed_to_modify__ = [GROUP_SUPERVISOR, GROUP_DIRECTOR]

    id = models.BigAutoField(primary_key=True)

    shop = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT)  # todo: make immutable
    position = models.ForeignKey(WorkerPosition, null=True, blank=True, on_delete=models.PROTECT)
    work_type = utils.EnumField(WorkType, null=True, blank=True)
    is_fixed_hours = models.BooleanField(default=False)
    is_fixed_days = models.BooleanField(default=False)
    group = models.CharField(
        max_length=1,
        default=GROUP_CASHIER,
        choices=GROUP_TYPE
    )
    # permissions = models.BigIntegerField(default=0)

    middle_name = models.CharField(max_length=64, blank=True, null=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    dt_hired = models.DateField(null=True, blank=True)
    dt_fired = models.DateField(null=True, blank=True)

    birthday = models.DateField(null=True, blank=True)
    SEX_FEMALE = 'F'
    SEX_MALE = 'M'
    SEX_CHOICES = (
        (SEX_FEMALE, 'Female',),
        (SEX_MALE, 'Male',),
    )
    sex = models.CharField(
        max_length=1,
        default=SEX_FEMALE,
        choices=SEX_CHOICES,
    )
    avatar = models.ImageField(null=True, blank=True, upload_to='user_avatar/%Y/%m')

    comment = models.CharField(max_length=2048, default='', blank=True)
    extra_info = models.CharField(max_length=512, default='', blank=True)

    auto_timetable = models.BooleanField(default=True)

    tabel_code = models.CharField(max_length=15, null=True, blank=True)
    phone_number = models.CharField(max_length=32, null=True, blank=True)
    is_ready_for_overworkings = models.BooleanField(default=False)

    objects = WorkerManager()


class CashboxType(models.Model):
    class Meta:
        verbose_name = 'Тип кассы'
        verbose_name_plural = 'Типы касс'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.name, self.shop.title, self.shop.super_shop.title, self.id)
        # return f'{self.name}, {self.shop.title}, {self.shop.super_shop.title}, {self.id}'

    id = models.BigAutoField(primary_key=True)

    priority = models.PositiveIntegerField(default=100)  # 1--main, 2-ord, 3-express, etc
    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)
    dttm_last_update_queue = models.DateTimeField(null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    name = models.CharField(max_length=128)
    speed_coef = models.FloatField(default=1)
    is_stable = models.BooleanField(default=True)
    FORECAST_HARD = 'H'
    FORECAST_LITE = 'L'
    FORECAST_NONE = 'N'
    FORECAST_CHOICES = (
        (FORECAST_HARD, 'Hard',),
        (FORECAST_LITE, 'Lite',),
        (FORECAST_NONE, 'None',),
    )
    do_forecast = models.CharField(
        max_length=1,
        default=FORECAST_LITE,
        choices=FORECAST_CHOICES,
    )
    probability = models.FloatField(default=1.0)
    prior_weight = models.FloatField(default=1.0)
    is_main_type = models.BooleanField(default=False)


class UserWeekdaySlot(models.Model):
    def __str__(self):
        # return f'{self.worker.last_name}, {self.slot.name}, {self.weekday}, {self.id}'
        return '{}, {}, {}, {}'.format(self.worker.last_name, self.slot.name, self.weekday, self.id)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    slot = models.ForeignKey('Slot', on_delete=models.CASCADE)
    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday


class Slot(models.Model):
    class Meta:
        # FIXME: уточнить значение
        verbose_name = 'Слот'
        verbose_name_plural = 'Слоты'

    def __str__(self):
        if self.cashbox_type:
            cbt_name = self.cashbox_type.name
        else:
            cbt_name = None
        return '{}, {}, {}, {}, {}'.format(self.name, cbt_name, self.shop.title, self.shop.super_shop.title, self.id)
        # return f'{self.name}, {cbt_name}, {self.shop.title}, {self.shop.super_shop.title}, {self.id}'

    id = models.BigAutoField(primary_key=True)

    tm_start = models.TimeField(default=datetime.time(hour=7))
    tm_end = models.TimeField(default=datetime.time(hour=23, minute=59, second=59))
    name = models.CharField(max_length=32, null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    cashbox_type = models.ForeignKey(CashboxType, null=True, blank=True, on_delete=models.PROTECT)

    worker = models.ManyToManyField(User, through=UserWeekdaySlot)


class CashboxManager(models.Manager):
    def qos_filter_active(self, dt_from, dt_to, *args, **kwargs):
        """
        added earlier then dt_from, added later then dt_to
        :param dt_from:
        :param dt_to:
        :param args:
        :param kwargs:
        :return:
        """

        return self.filter(
            models.Q(dttm_added__lte=dt_from) | models.Q(dttm_added__isnull=True)
        ).filter(
            models.Q(dttm_deleted__gte=dt_to) | models.Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)


class Cashbox(models.Model):
    class Meta:
        verbose_name = 'Касса'
        verbose_name_plural = 'Кассы'

    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(self.type.name, self.type.shop.title, self.type.shop.super_shop.title, self.id, self.number)
        # return f'{self.type.name}, {self.type.shop.title}, {self.type.shop.super_shop.title}, {self.id}'

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)

    number = models.PositiveIntegerField(blank=True, null=True)
    bio = models.CharField(max_length=512, default='', blank=True)
    objects = CashboxManager()


class PeriodDemand(models.Model):
    class Type(utils.Enum):
        LONG_FORECAST = 1  # 60 day
        SHORT_FORECAST = 2  # 10 day
        FACT = 3  # real

    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(self.cashbox_type.name, self.cashbox_type.shop.title, self.dttm_forecast,
                                           self.type, self.id)
        # return f'{self.cashbox_type.name}, {self.cashbox_type.shop.title}, {self.dttm_forecast}, {self.type}, {self.id}'

    id = models.BigAutoField(primary_key=True)

    dttm_forecast = models.DateTimeField()
    clients = models.FloatField()
    products = models.FloatField()

    type = utils.EnumField(Type)
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)

    queue_wait_time = models.FloatField()  # in minutes
    queue_wait_length = models.FloatField()
    lack_of_cashiers = models.IntegerField(default=0)  # can be both pos and neg


class PeriodDemandChangeLog(models.Model):
    # FIXME: как относится к PeriodDemand?
    def __str__(self):
        # return f'{self.cashbox_type.name}, {self.cashbox_type.shop.title}, {self.dttm_from}, {self.dttm_to}, {self.id}'
        return '{}, {}, {}, {}, {}'.format(self.cashbox_type.name, self.cashbox_type.shop.title, self.dttm_from, self.dttm_to, self.id)

    id = models.BigAutoField(primary_key=True)

    dttm_from = models.DateTimeField()
    dttm_to = models.DateTimeField()
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)
    multiply_coef = models.FloatField(null=True, blank=True)
    set_value = models.FloatField(null=True, blank=True)


class WorkerCashboxInfo(models.Model):
    class Meta(object):
        unique_together = (('worker', 'cashbox_type'),)

    def __str__(self):
        return '{}, {}, {}'.format(self.worker.last_name, self.cashbox_type.name, self.id)
        # return f'{self.worker.last_name}, {self.cashbox_type.name}, {self.id}'

    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT)

    is_active = models.BooleanField(default=True)

    period = models.PositiveIntegerField(default=90)  # show for how long in days the data was collect

    mean_speed = models.FloatField(default=1)
    bills_amount = models.PositiveIntegerField(default=0)
    priority = models.IntegerField(default=0)


class WorkerConstraint(models.Model):
    class Meta(object):
        unique_together = (('worker', 'weekday', 'tm'),)

    def __str__(self):
        return ''.format(self.worker.last_name, self.weekday, self.tm, self.id)
        # return f'{self.worker.last_name}, {self.weekday}, {self.tm}, {self.id}'

    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday
    tm = models.TimeField()


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
        TYPE_BUSINESS_TRIP = 8

        TYPE_ETC = 9
        TYPE_DELETED = 10
        TYPE_EMPTY = 11

        TYPE_HOLIDAY_WORK = 12
        TYPE_REAL_ABSENCE = 13
        TYPE_EXTRA_VACATION = 14
        TYPE_TRAIN_VACATION = 15
        TYPE_SELF_VACATION = 16
        TYPE_SELF_VACATION_TRUE = 17
        TYPE_GOVERNMENT = 18
        TYPE_HOLIDAY_SPECIAL = 19

        TYPE_MATERNITY_CARE = 20
        TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE = 21

    TYPES_PAID = [
        Type.TYPE_WORKDAY.value,
        Type.TYPE_QUALIFICATION.value,
        Type.TYPE_VACATION.value,
        Type.TYPE_BUSINESS_TRIP.value,
        Type.TYPE_HOLIDAY_WORK.value,
        Type.TYPE_EXTRA_VACATION.value,
        Type.TYPE_TRAIN_VACATION.value,
    ]


    def __str__(self):
        # return f'{self.worker.last_name}, {self.worker.shop.title}, {self.worker.shop.super_shop.title}, {self.dt},' \
        #        f' {self.Type.get_name_by_value(self.type)}, {self.id}'
        return '{}, {}, {}, {}, {}, {}'.format(self.worker.last_name, self.worker.shop.title, self.worker.shop.super_shop.title, self.dt, self.Type.get_name_by_value(self.type), self.id)

    def __repr__(self):
        return self.__str__()

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    worker = models.ForeignKey(User, on_delete=models.PROTECT)  # todo: make immutable
    dt = models.DateField()  # todo: make immutable
    type = utils.EnumField(Type)

    tm_work_start = models.TimeField(null=True, blank=True)
    tm_work_end = models.TimeField(null=True, blank=True)
    tm_break_start = models.TimeField(null=True, blank=True)

    is_manual_tuning = models.BooleanField(default=False)
    cashbox_types = models.ManyToManyField(CashboxType, through='WorkerDayCashboxDetails')

    @classmethod
    def is_type_with_tm_range(cls, t):
        return t in (cls.Type.TYPE_WORKDAY.value, cls.Type.TYPE_BUSINESS_TRIP.value, cls.Type.TYPE_QUALIFICATION.value)


class WorkerDayCashboxDetails(models.Model):
    TYPE_WORK = 'W'
    TYPE_BREAK = 'B'
    TYPE_STUDY = 'S'

    TYPE_SOON = 'C'
    TYPE_FINISH = 'H'
    TYPE_ABSENCE = 'A'

    DETAILS_TYPES = (
            (TYPE_WORK, 'work period'),
            (TYPE_BREAK, 'rest / break'),
            (TYPE_STUDY, 'study period'),
    )

    TYPE_T = 'T'

    WORK_TYPES_LIST = (
        TYPE_WORK,
        TYPE_STUDY
    )

    DETAILS_TYPES_LIST = (
        TYPE_WORK,
        TYPE_BREAK,
        TYPE_STUDY
    )

    id = models.BigAutoField(primary_key=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)
    on_cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT, null=True, blank=True)
    cashbox_type = models.ForeignKey(CashboxType, on_delete=models.PROTECT, null=True, blank=True)

    status = models.CharField(max_length=1, choices=DETAILS_TYPES, default=TYPE_WORK)

    is_tablet = models.BooleanField(default=False)

    tm_from = models.TimeField()
    tm_to = models.TimeField(null=True, blank=True)

    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(self.worker_day.worker.last_name, self.worker_day.worker.shop.super_shop.title, self.worker_day.dt, self.cashbox_type.name, self.id)


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
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.worker_day.worker.last_name, self.worker_day.worker.shop.super_shop.title, self.worker_day.dt, self.id)
        # return f'{self.worker_day.worker.last_name}, {self.worker_day.worker.shop.super_shop.title},' \
        #        f' {self.worker_day.dt}, {self.id}'

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
    comment = models.CharField(max_length=128, default='', blank=True)


class Notifications(models.Model):
    TYPE_SUCCESS = 'S'
    TYPE_INFO = 'I'
    TYPE_WARNING = 'W'
    TYPE_ERROR = 'E'

    TYPES = (
        (TYPE_SUCCESS, 'success'),
        (TYPE_INFO, 'info'),
        (TYPE_WARNING, 'warning'),
        (TYPE_ERROR, 'error')
    )

    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(self.to_worker.last_name, self.to_worker.shop.title, self.to_worker.shop.super_shop.title, self.dttm_added, self.id)
        # return f'{self.to_worker.last_name}, {self.to_worker.shop.title}, {self.to_worker.shop.super_shop.title}, ' \
        #        f'{self.dttm_added}, {self.id}'

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    to_worker = models.ForeignKey(User, on_delete=models.PROTECT)

    was_read = models.BooleanField(default=False)

    text = models.CharField(max_length=512)
    type = models.CharField(max_length=1, choices=TYPES, default=TYPE_SUCCESS)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    object = GenericForeignKey(ct_field='content_type', fk_field='object_id')


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

    task_id = models.CharField(max_length=256, null=True, blank=True)


class ProductionMonth(models.Model):
    """
    производственный календарь

    """

    dt_first = models.DateField()
    total_days = models.SmallIntegerField()
    norm_work_days = models.SmallIntegerField()
    norm_work_hours = models.FloatField()

    class Meta:
        ordering = ('dt_first',)


class ProductionDay(models.Model):
    """
    день из производственного календаря короч.

    """

    TYPE_WORK = 'W'
    TYPE_HOLIDAY = 'H'
    TYPE_SHORT_WORK = 'S'
    TYPES = (
        (TYPE_WORK, 'workday'),
        (TYPE_HOLIDAY, 'holiday'),
        (TYPE_SHORT_WORK, 'short workday')
    )

    WORK_TYPES = [
        TYPE_WORK,
        TYPE_SHORT_WORK
    ]

    WORK_NORM_HOURS = {
        TYPE_WORK: 8,
        TYPE_SHORT_WORK: 7,
        TYPE_HOLIDAY: 0
    }

    dt = models.DateField(unique=True)
    type = models.CharField(max_length=1, choices=TYPES)
    is_celebration = models.BooleanField(default=False)

    def __str__(self):
        # return f'{self.worker.last_name}, {self.worker.shop.title}, {self.worker.shop.super_shop.title}, {self.dt},' \
        #        f' {self.Type.get_name_by_value(self.type)}, {self.id}'

        for tp in self.TYPES:
            if tp[0] == self.type:
                break
        else:
            tp = ('', 'bad_bal')

        return '(dt {}, type {}, id {})'.format(self.dt, self.type, self.id)

    def __repr__(self):
        return self.__str__()
    
    # is it enough or work hours also needs?


class WorkerMonthStat(models.Model):
    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    month = models.ForeignKey(ProductionMonth, on_delete=models.PROTECT)

    work_days = models.SmallIntegerField()
    work_hours = models.FloatField()


class CameraCashbox(models.Model):
    name = models.CharField(max_length=64)
    cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self):
        return '{}, {}, {}'.format(self.name, self.cashbox, self.id)


class CameraCashboxStat(models.Model):
    camera_cashbox = models.ForeignKey(CameraCashbox, on_delete=models.PROTECT)
    dttm = models.DateTimeField()
    queue = models.FloatField()

    def __str__(self):
        return '{}, {}, {}'.format(self.dttm, self.camera_cashbox.name, self.id)


