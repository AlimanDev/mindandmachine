from django.db import models
from django.contrib.auth.models import (
    AbstractUser as DjangoAbstractUser,
    UserManager
)
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from . import utils
import datetime


class Region(models.Model):
    title = models.CharField(max_length=256, unique=True, default='Москва')


# магазин
class SuperShop(models.Model):
    class Meta:
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'

    id = models.BigAutoField(primary_key=True)

    TYPE_HYPERMARKET = 'H'
    TYPE_COMMON = 'C'

    SIZE_TYPES = (
        (TYPE_HYPERMARKET, 'hypermarket'),
        (TYPE_COMMON, 'common supershop'),
    )

    title = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=64, null=True, blank=True)

    dt_opened = models.DateField(null=True, blank=True)
    dt_closed = models.DateField(null=True, blank=True)

    tm_start = models.TimeField(null=True, blank=True, default=datetime.time(hour=7))
    tm_end = models.TimeField(null=True, blank=True, default=datetime.time(hour=23, minute=59, second=59))
    type = models.CharField(max_length=1, choices=SIZE_TYPES, default=TYPE_COMMON)
    region = models.ForeignKey(Region, blank=True, null=True, on_delete=models.PROTECT)
    address = models.CharField(max_length=256, blank=True, null=True)

    def __str__(self):
        return '{}, {}, {}'.format(self.title, self.code, self.id)

    def is_supershop_open_at(self, tm):
        if self.tm_start < self.tm_end:
            return self.tm_start < tm < self.tm_end
        else:
            if tm > self.tm_start:
                return True
            else:
                return tm < self.tm_end


# на самом деле это отдел
class Shop(models.Model):
    class Meta(object):
        unique_together = ('super_shop', 'title')
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'

    PRODUCTION_CAL = 'P'
    YEAR_NORM = 'N'

    PROCESS_TYPE = (
        (PRODUCTION_CAL, 'production calendar'),
        (YEAR_NORM, 'norm per year')
    )

    id = models.BigAutoField(primary_key=True)

    super_shop = models.ForeignKey(SuperShop, on_delete=models.PROTECT)
    full_interface = models.BooleanField(default=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    title = models.CharField(max_length=64)

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

    # added on 21.12.2018
    idle = models.SmallIntegerField(default=0)  # percents
    fot = models.IntegerField(default=0)
    less_norm = models.SmallIntegerField(default=0)  # percents
    more_norm = models.SmallIntegerField(default=0)  # percents
    tm_shop_opens = models.TimeField(default=datetime.time(6, 0))
    tm_shop_closes = models.TimeField(default=datetime.time(23, 0))
    shift_start = models.SmallIntegerField(default=6)
    shift_end = models.SmallIntegerField(default=12)
    restricted_start_times = models.CharField(max_length=1024, default='[]')
    restricted_end_times = models.CharField(max_length=1024, default='[]')
    min_change_time = models.IntegerField(default=12)
    even_shift_morning_evening = models.BooleanField(default=False)
    paired_weekday = models.BooleanField(default=False)
    exit1day = models.BooleanField(default=False)
    exit42hours = models.BooleanField(default=False)
    process_type = models.CharField(max_length=1, choices=PROCESS_TYPE, default=YEAR_NORM)

    def __str__(self):
        return '{}, {}, {}'.format(self.title, self.super_shop.title, self.id)


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
            models.Q(dt_hired__lte=dt_from) | models.Q(dt_hired__isnull=True),
            attachment_group=User.GROUP_STAFF
        ).filter(
            models.Q(dt_fired__gte=dt_to) | models.Q(dt_fired__isnull=True),
            attachment_group=User.GROUP_STAFF
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

    GROUP_STAFF = 'S'
    GROUP_OUTSOURCE = 'O'

    ATTACHMENT_TYPE = (
        (GROUP_STAFF, 'staff'),
        (GROUP_OUTSOURCE, 'outsource'),
    )

    __all_groups__ = [x[0] for x in GROUP_TYPE]
    __except_cashiers__ = [GROUP_MANAGER, GROUP_SUPERVISOR, GROUP_DIRECTOR, GROUP_HQ]
    __allowed_to_modify__ = [GROUP_SUPERVISOR, GROUP_DIRECTOR]

    id = models.BigAutoField(primary_key=True)
    position = models.ForeignKey(WorkerPosition, null=True, blank=True, on_delete=models.PROTECT)
    shop = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT)  # todo: make immutable
    work_type = utils.EnumField(WorkType, null=True, blank=True)
    is_fixed_hours = models.BooleanField(default=False)
    is_fixed_days = models.BooleanField(default=False)
    group = models.CharField(
        max_length=1,
        default=GROUP_CASHIER,
        choices=GROUP_TYPE
    )
    attachment_group = models.CharField(
        max_length=1,
        default=GROUP_STAFF,
        choices=ATTACHMENT_TYPE
    )

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


class WorkTypeManager(models.Manager):
    def qos_filter_active(self, dt_from, dt_to, *args, **kwargs):
        """
        added earlier then dt_from, deleted later then dt_to
        :param dttm_from:
        :param dttm_to:
        :param args:
        :param kwargs:
        :return:
        """

        return self.filter(
            models.Q(dttm_added__date__lte=dt_from) | models.Q(dttm_added__isnull=True)
        ).filter(
            models.Q(dttm_deleted__date__gte=dt_to) | models.Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)


class WorkType(models.Model):
    class Meta:
        verbose_name = 'Тип работ'
        verbose_name_plural = 'Типы работ'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.name, self.shop.title, self.shop.super_shop.title, self.id)

    id = models.BigAutoField(primary_key=True)

    priority = models.PositiveIntegerField(default=100)  # 1--главная касса, 2--линия, 3--экспресс
    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)
    dttm_last_update_queue = models.DateTimeField(null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    name = models.CharField(max_length=128)

    probability = models.FloatField(default=1.0)
    prior_weight = models.FloatField(default=1.0)
    objects = WorkTypeManager()

    period_queue_params = models.CharField(
        max_length=1024,
        default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 1, "reg_lambda": 0.1, "silent": 1, "iterations": 20}'
    )


class OperationType(models.Model):
    def __str__(self):
        return 'id: {}, name: {}, work type: {}'.format(self.id, self.name, self.work_type)

    FORECAST_HARD = 'H'
    FORECAST_LITE = 'L'
    FORECAST_NONE = 'N'
    FORECAST_CHOICES = (
        (FORECAST_HARD, 'Hard',),
        (FORECAST_LITE, 'Lite',),
        (FORECAST_NONE, 'None',),
    )

    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, related_name='work_type_reversed')
    name = models.CharField(max_length=128)
    speed_coef = models.FloatField(default=1)  # time for do 1 operation
    do_forecast = models.CharField(
        max_length=1,
        default=FORECAST_LITE,
        choices=FORECAST_CHOICES,
    )

    period_demand_params = models.CharField(
        max_length=1024,
        default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 200, "reg_lambda": 2, "silent": 1, "iterations": 20}'
    )


class UserWeekdaySlot(models.Model):
    def __str__(self):
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
        if self.work_type:
            cbt_name = self.work_type.name
        else:
            cbt_name = None
        return '{}, начало: {}, конец: {}, {}, {}, {}'.format(
            cbt_name,
            self.tm_start,
            self.tm_end,
            self.shop.title,
            self.shop.super_shop.title,
            self.id)

    id = models.BigAutoField(primary_key=True)

    tm_start = models.TimeField(default=datetime.time(hour=7))
    tm_end = models.TimeField(default=datetime.time(hour=23, minute=59, second=59))
    name = models.CharField(max_length=32, null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    work_type = models.ForeignKey(WorkType, null=True, blank=True, on_delete=models.PROTECT)
    workers_needed = models.IntegerField(default=1)

    worker = models.ManyToManyField(User, through=UserWeekdaySlot)


class CashboxManager(models.Manager):
    def qos_filter_active(self, dt_from, dt_to, *args, **kwargs):
        """
        added earlier then dt_from, deleted later then dt_to
        :param dt_from:
        :param dt_to:
        :param args:
        :param kwargs:
        :return:
        """

        return self.filter(
            models.Q(dttm_added__date__lte=dt_from) | models.Q(dttm_added__isnull=True)
        ).filter(
            models.Q(dttm_deleted__date__gt=dt_to) | models.Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)


class Cashbox(models.Model):
    class Meta:
        verbose_name = 'Касса'
        verbose_name_plural = 'Кассы'

    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(
            self.type.name,
            self.type.shop.title,
            self.type.shop.super_shop.title,
            self.id,
            self.number
        )

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    type = models.ForeignKey(WorkType, on_delete=models.PROTECT)

    number = models.PositiveIntegerField(blank=True, null=True)
    bio = models.CharField(max_length=512, default='', blank=True)
    objects = CashboxManager()


class PeriodDemand(models.Model):
    LONG_FORECASE_TYPE = 'L'
    SHORT_FORECAST_TYPE = 'S'
    FACT_TYPE = 'F'

    FORECAST_TYPES = (
        (LONG_FORECASE_TYPE, 'Long'),
        (SHORT_FORECAST_TYPE, 'Short'),
        (FACT_TYPE, 'Fact'),
    )

    class Meta:
        abstract = True

    id = models.BigAutoField(primary_key=True)
    dttm_forecast = models.DateTimeField()
    type = models.CharField(choices=FORECAST_TYPES, max_length=1, default=LONG_FORECASE_TYPE)
    operation_type = models.ForeignKey(OperationType, on_delete=models.PROTECT)


class PeriodClients(PeriodDemand):
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    value = models.FloatField(default=0)


class PeriodProducts(PeriodDemand):
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    value = models.FloatField(default=0)


class PeriodQueues(PeriodDemand):
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    value = models.FloatField(default=0)


class PeriodVisitors(models.Model):
    LONG_FORECASE_TYPE = 'L'
    SHORT_FORECAST_TYPE = 'S'
    FACT_TYPE = 'F'

    FORECAST_TYPES = (
        (LONG_FORECASE_TYPE, 'Long'),
        (SHORT_FORECAST_TYPE, 'Short'),
        (FACT_TYPE, 'Fact'),
    )

    class Meta:
        abstract = True

    id = models.BigAutoField(primary_key=True)
    dttm_forecast = models.DateTimeField()
    type = models.CharField(choices=FORECAST_TYPES, max_length=1, default=LONG_FORECASE_TYPE)
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT)


class IncomeVisitors(PeriodVisitors):
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.work_type, self.value)

    value = models.FloatField(default=0)


class EmptyOutcomeVisitors(PeriodVisitors):
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.work_type, self.value)

    value = models.FloatField(default=0)


class PurchasesOutcomeVisitors(PeriodVisitors):
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.work_type, self.value)

    value = models.FloatField(default=0)


class PeriodDemandChangeLog(models.Model):
    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(
            self.operation_type.name,
            self.operation_type.work_type.shop.title,
            self.dttm_from,
            self.dttm_to,
            self.id
        )

    id = models.BigAutoField(primary_key=True)
    dttm_added = models.DateTimeField(auto_now_add=True)

    dttm_from = models.DateTimeField()
    dttm_to = models.DateTimeField()
    operation_type = models.ForeignKey(OperationType, on_delete=models.PROTECT)
    multiply_coef = models.FloatField(null=True, blank=True)
    set_value = models.FloatField(null=True, blank=True)


class WorkerCashboxInfo(models.Model):
    class Meta(object):
        unique_together = (('worker', 'work_type'),)

    def __str__(self):
        return '{}, {}, {}'.format(self.worker.last_name, self.work_type.name, self.id)

    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT)

    is_active = models.BooleanField(default=True)

    period = models.PositiveIntegerField(default=90)  # show for how long in days the data was collect

    mean_speed = models.FloatField(default=1)
    bills_amount = models.PositiveIntegerField(default=0)
    priority = models.IntegerField(default=0)

    # how many hours did he work
    duration = models.FloatField(default=0)


class WorkerConstraint(models.Model):
    class Meta(object):
        unique_together = (('worker', 'weekday', 'tm'),)

    def __str__(self):
        return '{} {}, {}, {}, {}'.format(self.worker.last_name, self.worker.id, self.weekday, self.tm, self.id)

    id = models.BigAutoField(primary_key=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday
    is_lite = models.BooleanField(default=False)  # True -- если сам сотрудник выставил, False -- если менеджер
    tm = models.TimeField()


class WorkerDayManager(models.Manager):
    def qos_current_version(self):
        return super().get_queryset().filter(child__id__isnull=True)

    def qos_initial_version(self):
        return super().get_queryset().filter(parent_worker_day__isnull=True)

    def qos_filter_version(self, checkpoint):
        """
        :param checkpoint: 0 or 1 / True of False. If 1 -- current version, else -- initial
        :return:
        """
        if checkpoint:
            return self.qos_current_version()
        else:
            return self.qos_initial_version()


class WorkerDay(models.Model):
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
        return '{}, {}, {}, {}, {}, {}'.format(
            self.worker.last_name,
            self.worker.shop.title,
            self.worker.shop.super_shop.title,
            self.dt,
            self.Type.get_name_by_value(self.type),
            self.id
        )

    def __repr__(self):
        return self.__str__()

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dt = models.DateField()  # todo: make immutable
    dttm_work_start = models.DateTimeField(null=True, blank=True)
    dttm_work_end = models.DateTimeField(null=True, blank=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)  # todo: make immutable
    type = utils.EnumField(Type)

    work_types = models.ManyToManyField(WorkType, through='WorkerDayCashboxDetails')

    created_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, related_name='user_created')
    parent_worker_day = models.OneToOneField('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='child')

    @classmethod
    def is_type_with_tm_range(cls, t):
        return t in (cls.Type.TYPE_WORKDAY.value, cls.Type.TYPE_BUSINESS_TRIP.value, cls.Type.TYPE_QUALIFICATION.value)

    objects = WorkerDayManager()


class WorkerDayCashboxDetailsManager(models.Manager):
    def qos_current_version(self):
        return super().get_queryset().select_related('worker_day').filter(worker_day__child__id__isnull=True)

    def qos_initial_version(self):
        return super().get_queryset().select_related('worker_day').filter(worker_day__parent_worker_day__isnull=True)

    def qos_filter_version(self, checkpoint):
        """
        :param checkpoint: 0 or 1 / True of False. If 1 -- current version, else -- initial
        :return:
        """
        if checkpoint:
            return self.qos_current_version()
        else:
            return self.qos_initial_version()


class WorkerDayCashboxDetails(models.Model):
    TYPE_WORK = 'W'
    TYPE_WORK_TRADING_FLOOR = 'Z'
    TYPE_BREAK = 'B'
    TYPE_STUDY = 'S'

    TYPE_SOON = 'C'
    TYPE_FINISH = 'H'
    TYPE_ABSENCE = 'A'

    DETAILS_TYPES = (
            (TYPE_WORK, 'work period'),
            (TYPE_BREAK, 'rest / break'),
            (TYPE_STUDY, 'study period'),
            (TYPE_WORK_TRADING_FLOOR, 'work in trading floor'),
    )

    TYPE_T = 'T'

    WORK_TYPES_LIST = (
        TYPE_WORK,
        TYPE_STUDY,
        TYPE_WORK_TRADING_FLOOR,
    )

    DETAILS_TYPES_LIST = (
        TYPE_WORK,
        TYPE_BREAK,
        TYPE_STUDY,
        TYPE_WORK_TRADING_FLOOR,
    )

    id = models.BigAutoField(primary_key=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT)
    on_cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT, null=True, blank=True)
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, null=True, blank=True)

    status = models.CharField(max_length=1, choices=DETAILS_TYPES, default=TYPE_WORK)

    is_tablet = models.BooleanField(default=False)

    dttm_from = models.DateTimeField()
    dttm_to = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return '{}, {}, {}, {}-{}, id: {}'.format(
            self.worker_day.worker.last_name,
            self.worker_day.dt,
            self.work_type.name if self.work_type else None,
            self.dttm_from.replace(microsecond=0).time() if self.dttm_from else self.dttm_from,
            self.dttm_to.replace(microsecond=0).time() if self.dttm_to else self.dttm_to,
            self.id,
        )

    objects = WorkerDayCashboxDetailsManager()


class WorkerDayChangeRequest(models.Model):
    def __str__(self):
        return '{}, {}, {}'.format(self.worker.id, self.dt, self.status_type)

    class Meta(object):
        unique_together = ('worker', 'dt')

    TYPE_APPROVED = 'A'
    TYPE_DECLINED = 'D'
    TYPE_PENDING = 'P'

    STATUS_CHOICES = (
        (TYPE_APPROVED, 'Approved'),
        (TYPE_DECLINED, 'Declined'),
        (TYPE_PENDING, 'Pending'),
    )

    id = models.BigAutoField(primary_key=True)
    dttm_added = models.DateTimeField(auto_now_add=True)
    status_type = models.CharField(max_length=1, choices=STATUS_CHOICES, default=TYPE_PENDING)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    dt = models.DateField()
    type = utils.EnumField(WorkerDay.Type)

    dttm_work_start = models.DateTimeField(null=True, blank=True)
    dttm_work_end = models.DateTimeField(null=True, blank=True)
    wish_text = models.CharField(null=True, blank=True, max_length=512)


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
        return '{}, {}, {}, text: {}, id: {}'.format(
            self.to_worker.last_name,
            self.to_worker.shop.title,
            self.dttm_added,
            self.text[:60],
            self.id
        )

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
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT)
    wait_time = models.PositiveIntegerField()
    proportion = models.FloatField()
    type = models.CharField(max_length=1, choices=PeriodDemand.FORECAST_TYPES)


class Timetable(models.Model):
    class Meta(object):
        unique_together = (('shop', 'dt'),)

    class Status(utils.Enum):
        READY = 1
        PROCESSING = 2
        ERROR = 3

    id = models.BigAutoField(primary_key=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    status_message = models.CharField(max_length=256, null=True, blank=True)
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

        for tp in self.TYPES:
            if tp[0] == self.type:
                break
        else:
            tp = ('', 'bad_bal')

        return '(dt {}, type {}, id {})'.format(self.dt, self.type, self.id)


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


class CameraClientGate(models.Model):
    TYPE_ENTRY = 'E'
    TYPE_OUT = 'O'
    TYPE_SERVICE = 'S'

    GATE_TYPES = (
        (TYPE_ENTRY, 'entry'),
        (TYPE_OUT, 'exit'),
        (TYPE_SERVICE, 'service')
    )

    name = models.CharField(max_length=64)
    type = models.CharField(max_length=1, choices=GATE_TYPES)

    def __str__(self):
        return '{}, {}'.format(self.type, self.name)


class CameraClientEvent(models.Model):
    TYPE_TOWARD = 'T'
    TYPE_BACKWARD = 'B'

    DIRECTION_TYPES = (
        (TYPE_TOWARD, 'toward'),
        (TYPE_BACKWARD, 'backward')
    )

    dttm = models.DateTimeField()
    gate = models.ForeignKey(CameraClientGate, on_delete=models.PROTECT)
    type = models.CharField(max_length=1, choices=DIRECTION_TYPES)

    def __str__(self):
        return 'id {}: {}, {}, {}'.format(self.id, self.dttm, self.type, self.gate.name)


class UserIdentifier(models.Model):
    dttm_added = models.DateTimeField(auto_now_add=True)
    identifier = models.CharField(max_length=256, unique=True)
    worker = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self):
        return 'id: {}, identifier: {}, worker: {}'.format(self.id, self.identifier, self.worker_id)


class AttendanceRecords(models.Model):
    TYPE_COMING = 'C'
    TYPE_LEAVING = 'L'
    TYPE_BREAK_START = 'S'
    TYPE_BREAK_END = 'E'

    RECORD_TYPES = (
        (TYPE_COMING, 'coming'),
        (TYPE_LEAVING, 'leaving'),
        (TYPE_BREAK_START, 'break start'),
        (TYPE_BREAK_END, 'break_end')
    )

    dttm = models.DateTimeField()
    type = models.CharField(max_length=1, choices=RECORD_TYPES)
    identifier = models.ForeignKey(UserIdentifier, on_delete=models.PROTECT)
    verified = models.BooleanField(default=True)

    super_shop = models.ForeignKey(SuperShop, on_delete=models.PROTECT) # todo: or should be to shop? fucking logic

    def __str__(self):
        return 'UserIdentID: {}, type: {}, dttm: {}'.format(self.identifier_id, self.type, self.dttm)
