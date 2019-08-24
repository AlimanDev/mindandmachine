from django.db import models
from django.contrib.auth.models import (
    AbstractUser as DjangoAbstractUser,
    UserManager
)
from django.contrib.contenttypes.models import ContentType
from . import utils
import datetime
from mptt.models import MPTTModel, TreeForeignKey

# на самом деле это отдел
class Shop(MPTTModel):
    def __init__(self, *args, **kwargs):
        super(Shop, self).__init__(*args, **kwargs)

    class Meta(object):
        # unique_together = ('parent', 'title')
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'

    PRODUCTION_CAL = 'P'
    YEAR_NORM = 'N'

    PROCESS_TYPE = (
        (PRODUCTION_CAL, 'production calendar'),
        (YEAR_NORM, 'norm per year')
    )

    id = models.BigAutoField(primary_key=True)

    parent = TreeForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='child')

    # full_interface = models.BooleanField(default=True)

    TYPE_REGION = 'r'
    TYPE_SHOP = 's'

    DEPARTMENT_TYPES = (
        (TYPE_REGION, 'region'),
        (TYPE_SHOP, 'shop'),
    )


    #From supershop
    code = models.CharField(max_length=64, null=True, blank=True)
    address = models.CharField(max_length=256, blank=True, null=True)
    type = models.CharField(max_length=1, choices=DEPARTMENT_TYPES, default=TYPE_SHOP)
    dt_opened = models.DateField(null=True, blank=True)
    dt_closed = models.DateField(null=True, blank=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    title = models.CharField(max_length=64)

    mean_queue_length = models.FloatField(default=3)
    max_queue_length = models.FloatField(default=7)
    dead_time_part = models.FloatField(default=0.1)

    beta = models.FloatField(default=0.9)  # for creating timetable, (a function from previous 3 variables)

    demand_coef = models.FloatField(default=1)  # unknown trend for algorithm

    forecast_step_minutes = models.TimeField(default=datetime.time(minute=30))
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
    # workdays_holidays_same = models.BooleanField(default=False)
    paired_weekday = models.BooleanField(default=False)
    exit1day = models.BooleanField(default=False)
    exit42hours = models.BooleanField(default=False)
    process_type = models.CharField(max_length=1, choices=PROCESS_TYPE, default=YEAR_NORM)
    absenteeism = models.SmallIntegerField(default=0)  # percents
    # added on 16.05.2019
    queue_length = models.FloatField(default=3.0)

    max_work_hours_7days = models.SmallIntegerField(default=48)

    staff_number = models.SmallIntegerField(default=0)

    def __str__(self):
        return '{}, {}, {}'.format(
            self.title,
            self.parent_title(),
            self.id)

    def system_step_in_minutes(self):
        return self.forecast_step_minutes.hour * 60 + self.forecast_step_minutes.minute

    def parent_title(self):
        return self.parent.title if self.parent else '',

    def get_level_of(self, shop):
        if self.id == shop.id:
            return 0
        if (self.level < shop.level and self.is_ancestor_of(shop)) \
            or (self.level > shop.level and self.is_descendant_of(shop)):
                return shop.level - self.level
        return None
    def get_ancestor_by_level_distance(self, level):
        if self.level == 0 or level==0:
            return self
        level = self.level - level if self.level > level else 0
        return self.get_ancestors().filter(level=level)[0]


class WorkerPosition(models.Model):
    """
    Describe employee's department and position
    """

    class Meta:
        verbose_name = 'Должность сотрудника'
        verbose_name_plural = 'Должности сотрудников'

    id = models.BigAutoField(primary_key=True)

    title = models.CharField(max_length=64)

    def __str__(self):
        return '{}, {}'.format(self.title, self.id)


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


class Group(models.Model):
    class Meta:
        verbose_name = 'Группа пользователей'
        verbose_name_plural = 'Группы пользователей'

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_modified = models.DateTimeField(blank=True, null=True)
    name = models.CharField(max_length=128)
    subordinates = models.ManyToManyField("self", blank=True)

    def __str__(self):
        return '{}, {}, {}'.format(
            self.id,
            self.name,
            self.subordinates.all() if self.subordinates.all() else ''
        )


class User(DjangoAbstractUser):

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        if self.shop and self.shop.parent:
            ss_title = self.shop.parent.title
        else:
            ss_title = None
        return '{}, {}, {}, {}'.format(self.first_name, self.last_name, ss_title, self.id)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_fio(self):
        return self.last_name + ' ' + self.first_name

    GROUP_STAFF = 'S'
    GROUP_OUTSOURCE = 'O'

    ATTACHMENT_TYPE = (
        (GROUP_STAFF, 'staff'),
        (GROUP_OUTSOURCE, 'outsource'),
    )

    id = models.BigAutoField(primary_key=True)
    position = models.ForeignKey(WorkerPosition, null=True, blank=True, on_delete=models.PROTECT)
    shop = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT)  # todo: make immutable
    is_fixed_hours = models.BooleanField(default=False)
    function_group = models.ForeignKey(Group, on_delete=models.PROTECT, blank=True, null=True)
    attachment_group = models.CharField(
        max_length=1,
        default=GROUP_STAFF,
        choices=ATTACHMENT_TYPE
    )

    middle_name = models.CharField(max_length=64, blank=True, null=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    dt_hired = models.DateField(default=datetime.date(2019, 1, 1))
    dt_fired = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)

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
    extra_info = models.CharField(max_length=512, default='', blank=True)

    # new worker restrictions
    week_availability = models.SmallIntegerField(default=7)
    norm_work_hours = models.SmallIntegerField(default=100)
    shift_hours_length_min = models.SmallIntegerField(blank=True, null=True)
    shift_hours_length_max = models.SmallIntegerField(blank=True, null=True)
    min_time_btw_shifts = models.SmallIntegerField(blank=True, null=True)

    auto_timetable = models.BooleanField(default=True)

    tabel_code = models.CharField(max_length=15, null=True, blank=True)
    phone_number = models.CharField(max_length=32, null=True, blank=True)
    is_ready_for_overworkings = models.BooleanField(default=False)

    objects = WorkerManager()


class FunctionGroup(models.Model):
    class Meta:
        verbose_name = 'Доступ к функциям'
        unique_together = (('func', 'group'), )

    TYPE_SELF = 'S'
    TYPE_SHOP = 'TS'
    TYPE_SUPERSHOP = 'TSS'
    TYPE_ALL = 'A'

    TYPES = (
        (TYPE_SELF, 'self'),
        (TYPE_SHOP, 'shop'),
        (TYPE_SUPERSHOP, 'supershop'),
        (TYPE_ALL, 'all')
    )

    FUNCS = (
        'get_cashboxes_open_time',
        'get_workers',
        'get_demand_change_logs',
        'edit_work_type',
        'get_cashboxes_used_resource',
        'get_notifications',
        'get_notifications2',
        'get_cashboxes_info',
        'get_department',
        'update_cashbox',
        'delete_work_type',
        'get_outsource_workers',
        'change_cashier_info',
        'get_not_working_cashiers_list',
        'get_table',
        'get_worker_day',
        'create_cashbox',
        'set_worker_day',
        'signout',
        'create_timetable',
        'get_regions',
        'get_slots',
        'get_user_urv',
        'get_cashboxes',
        'get_cashier_timetable',
        'select_cashiers',
        'request_worker_day',
        'add_outsource_workers',
        'set_worker_restrictions',
        'create_cashier',
        'get_cashiers_info',
        'create_work_type',
        'get_visitors_info',
        'get_time_distribution',
        'set_queue',
        'set_notifications_read',
        'get_status',
        'get_forecast',
        'get_cashiers_list',
        'get_change_request',
        'delete_timetable',
        'get_types',
        'get_all_slots',
        'get_cashiers_timetable',
        'set_demand',
        'dublicate_cashier_table',
        'get_month_stat',
        'handle_worker_day_request',
        'get_workers_to_exchange',
        'get_tabel',
        'delete_cashier',
        'get_worker_day_logs',
        'password_edit',
        'get_cashier_info',
        'change_cashier_status',
        'set_selected_cashiers',
        'get_indicators',
        'upload_demand',
        'upload_timetable',
        'change_user_urv',
        'get_parent',
        'delete_cashbox',
        'set_timetable',
        'delete_worker_day',
        'create_predbills_request',
        'process_forecast',
        'notify_workers_about_vacancy',
        'show_vacancy',
        'cancel_vacancy',
        'confirm_vacancy',
        'do_notify_action',
        'exchange_workers_day',

        # download/
        'get_demand_xlsx',
        'get_department_stats_xlsx',
        'get_timetable_xlsx',
        'get_urv_xlsx',

        # shop/
        'add_department',
        'edit_department',
        'get_department_list',
        'get_department_stats',
        'get_parameters',
        'set_parameters',
    )

    FUNCS_TUPLE = ((f, f) for f in FUNCS)

    __INSIDE_SHOP_TYPES__ = [TYPE_SHOP, TYPE_SUPERSHOP] # for notification

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_modified = models.DateTimeField(blank=True, null=True)
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name='allowed_functions', blank=True, null=True)
    func = models.CharField(max_length=128, choices=FUNCS_TUPLE)
    access_type = models.CharField(choices=TYPES, max_length=32)
    level_up = models.IntegerField(default=0)
    level_down = models.IntegerField(default=100)

    def __str__(self):
        return 'id: {}, group: {}, access_type: {}, func name: {}'.format(
            self.id,
            self.group,
            self.access_type,
            self.func,
        )


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
        return '{}, {}, {}, {}'.format(self.name, self.shop.title, self.shop.parent.title, self.id)

    id = models.BigAutoField(primary_key=True)

    priority = models.PositiveIntegerField(default=100)  # 1--главная касса, 2--линия, 3--экспресс
    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)
    dttm_last_update_queue = models.DateTimeField(null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    name = models.CharField(max_length=128)
    min_workers_amount = models.IntegerField(default=0, blank=True, null=True)
    max_workers_amount = models.IntegerField(default=20, blank=True, null=True)

    probability = models.FloatField(default=1.0)
    prior_weight = models.FloatField(default=1.0)
    objects = WorkTypeManager()

    period_queue_params = models.CharField(
        max_length=1024,
        default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 1, "reg_lambda": 0.1, "silent": 1, "iterations": 20}'
    )


class OperationType(models.Model):
    class Meta:
        verbose_name = 'Тип операции'
        verbose_name_plural = 'Типы операций'

    def __str__(self):
        return 'id: {}, name: {}, work type: {}'.format(self.id, self.name, self.work_type)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(blank=True, null=True)

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
    class Meta(object):
        verbose_name = 'Пользовательский слот'
        verbose_name_plural = 'Пользовательские слоты'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.worker.last_name, self.slot.name, self.weekday, self.id)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    slot = models.ForeignKey('Slot', on_delete=models.CASCADE)
    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday
    is_suitable = models.BooleanField(default=True)


class Slot(models.Model):
    class Meta:
        verbose_name = 'Слот'
        verbose_name_plural = 'Слоты'

    def __str__(self):
        if self.work_type:
            work_type_name = self.work_type.name
        else:
            work_type_name = None
        return '{}, начало: {}, конец: {}, {}, {}, {}'.format(
            work_type_name,
            self.tm_start,
            self.tm_end,
            self.shop.title,
            self.shop.parent.title,
            self.id
        )

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(blank=True, null=True)

    tm_start = models.TimeField(default=datetime.time(hour=7))
    tm_end = models.TimeField(default=datetime.time(hour=23, minute=59, second=59))
    name = models.CharField(max_length=32, null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT) # todo delete this by cashbox_type
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
            self.type.shop.parent.title,
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
    class Meta(object):
        verbose_name = 'Спрос по клиентам'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    value = models.FloatField(default=0)


class PeriodProducts(PeriodDemand):
    class Meta(object):
        verbose_name = 'Спрос по продуктам'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    value = models.FloatField(default=0)


class PeriodQueues(PeriodDemand):
    class Meta(object):
        verbose_name = 'Очереди'

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
    class Meta(object):
        verbose_name = 'Входящие посетители (по периодам)'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.work_type, self.value)

    value = models.FloatField(default=0)


class EmptyOutcomeVisitors(PeriodVisitors):
    class Meta(object):
        verbose_name = 'Выходящие без покупок посетители (по периодам)'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.work_type, self.value)

    value = models.FloatField(default=0)


class PurchasesOutcomeVisitors(PeriodVisitors):
    class Meta(object):
        verbose_name = 'Выходящие с покупками посетители (по периодам)'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.work_type, self.value)

    value = models.FloatField(default=0)


class PeriodDemandChangeLog(models.Model):
    class Meta(object):
        verbose_name = 'Лог изменений спроса'

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
        verbose_name = 'Информация по сотруднику-типу работ'
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
        verbose_name = 'Ограничения сотрудника'
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

    @staticmethod
    def qos_get_current_worker_day(worker_day):
        while True:
            current_worker_day = worker_day
            try:
                worker_day = worker_day.child
            except WorkerDay.child.RelatedObjectDoesNotExist:
                break
        return current_worker_day


class WorkerDay(models.Model):
    class Meta:
        verbose_name = 'Рабочий день сотрудника'
        verbose_name_plural = 'Рабочие дни сотрудников'

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
        Type.TYPE_BUSINESS_TRIP.value,
        Type.TYPE_HOLIDAY_WORK.value,
        Type.TYPE_EXTRA_VACATION.value,
        Type.TYPE_TRAIN_VACATION.value,
    ]

    def __str__(self):
        return '{}, {}, {}, {}, {}, {}'.format(
            self.worker.last_name,
            self.worker.shop.title,
            self.worker.shop.parent.title,
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
    # fixme: better change parent to child as usual check if this is the last version of WorkerDay

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
    class Meta:
        verbose_name = 'Детали в течение рабочего дня'

    TYPE_WORK = 'W'
    TYPE_WORK_TRADING_FLOOR = 'Z'
    TYPE_BREAK = 'B'
    TYPE_STUDY = 'S'
    TYPE_VACANCY = 'V'
    TYPE_SOON = 'C'
    TYPE_FINISH = 'H'
    TYPE_ABSENCE = 'A'
    TYPE_DELETED = 'D'

    DETAILS_TYPES = (
            (TYPE_WORK, 'work period'),
            (TYPE_BREAK, 'rest / break'),
            (TYPE_STUDY, 'study period'),
            (TYPE_VACANCY, 'vacancy'),
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

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.PROTECT, null=True, blank=True)
    on_cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT, null=True, blank=True)
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, null=True, blank=True)

    status = models.CharField(max_length=1, choices=DETAILS_TYPES, default=TYPE_WORK)
    is_vacancy = models.BooleanField(default=False)

    is_tablet = models.BooleanField(default=False)

    dttm_from = models.DateTimeField()
    dttm_to = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return '{}, {}, {}, {}, {}-{}, id: {}'.format(
            # self.worker_day.worker.last_name,
            self.dttm_from.date(),
            '', '',
            self.work_type.name if self.work_type else None,
            self.dttm_from.replace(microsecond=0).time() if self.dttm_from else self.dttm_from,
            self.dttm_to.replace(microsecond=0).time() if self.dttm_to else self.dttm_to,
            self.id,
        )

    objects = WorkerDayCashboxDetailsManager()


class WorkerDayChangeRequest(models.Model):
    class Meta(object):
        verbose_name = 'Запрос на изменения рабочего дня'
        unique_together = ('worker', 'dt')

    def __str__(self):
        return '{}, {}, {}'.format(self.worker.id, self.dt, self.status_type)

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



class EventManager(models.Manager):
    def mm_event_create(self, users, push_title=None, **kwargs):
        event = self.create(**kwargs)

        # users = User.objects.filter(
        #     function_group__allowed_functions__func=noti_groups['func'],
        #     function_group__allowed_functions__access_type__in=noti_groups['access_types'],
        # )
        # if event.department:
        #     users = users.filter(shop=event.department)

        notis = Notifications.objects.bulk_create([Notifications(event=event, to_worker=u) for u in users])
        # todo: add sending push notifies
        return event


class Event(models.Model):
    dttm_added = models.DateTimeField(auto_now_add=True)

    text = models.CharField(max_length=256)
    # hidden_text = models.CharField(max_length=256, default='')

    department = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT) # todo: should be department model?

    workerday_details = models.ForeignKey(WorkerDayCashboxDetails, null=True, blank=True, on_delete=models.PROTECT)

    objects = EventManager()

    def get_text(self):
        if self.workerday_details:
            from src.util.models_converter import BaseConverter

            if self.workerday_details.dttm_deleted:
                return 'Вакансия отмена'
            elif self.workerday_details.worker_day_id:
                return 'Вакансия на {} в {} уже выбрана.'.format(
                    BaseConverter.convert_date(self.workerday_details.dttm_from.date()),
                    self.workerday_details.work_type.shop.title,
                )
            else:
                return 'Открыта вакансия на {} в {}. Время работы: с {} по {}. Хотите выйти?'.format(
                    BaseConverter.convert_date(self.workerday_details.dttm_from.date()),
                    self.workerday_details.work_type.shop.title,
                    BaseConverter.convert_time(self.workerday_details.dttm_from.time()),
                    BaseConverter.convert_time(self.workerday_details.dttm_to.time()),
                )

        else:
            return self.text

    def is_question(self):
        return not self.workerday_details_id is None

    def do_action(self, user):
        res = {
            'status': 0,
            'text': '',
        }

        if self.workerday_details_id: # действие -- выход на вакансию
            vacancy = self.workerday_details
            user_worker_day = WorkerDay.objects.qos_current_version().filter(
                worker=user,
                dt=vacancy.dttm_from.date()
            ).first()

            if user_worker_day and vacancy:
                is_updated = False
                update_condition = user_worker_day.type != WorkerDay.Type.TYPE_WORKDAY.value or \
                                   WorkerDayCashboxDetails.objects.filter(
                                       models.Q(dttm_from__gte=vacancy.dttm_from, dttm_from__lt=vacancy.dttm_to) |
                                       models.Q(dttm_to__gt=vacancy.dttm_from, dttm_to__lte=vacancy.dttm_to) |
                                       models.Q(dttm_from__lte=vacancy.dttm_from, dttm_to__gte=vacancy.dttm_to),
                                       worker_day_id=user_worker_day.id,
                                       dttm_deleted__isnull=True,
                                   ).count() == 0

                # todo: actually should be transaction (check condition and update)
                # todo: add time for go between shops
                if update_condition:
                    is_updated = WorkerDayCashboxDetails.objects.filter(
                        id=vacancy.id,
                        worker_day__isnull=True,
                        dttm_deleted__isnull=True,
                    ).update(
                        worker_day_id=user_worker_day.id,
                        status=WorkerDayCashboxDetails.TYPE_WORK,
                    )

                    if is_updated:
                        user_worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value

                        if (user_worker_day.dttm_work_start is None) or (user_worker_day.dttm_work_start > vacancy.dttm_from):
                            user_worker_day.dttm_work_start = vacancy.dttm_from

                        if (user_worker_day.dttm_work_end is None) or (user_worker_day.dttm_work_end < vacancy.dttm_to):
                            user_worker_day.dttm_work_end = vacancy.dttm_to

                        user_worker_day.save()

                    if not is_updated:
                        res['status'] = 3
                        res['text'] = 'Невозможно выполнить действие'

                else:
                    res['status'] = 4
                    res['text'] = 'Вы не можете выйти на эту смену'
            else:
                res['status'] = 2
                res['text'] = 'График на этот период еще не составлен'
        else:
            res['status'] = 1
            res['text'] = 'К этому уведомлению не может быть действия'
        return res

    def is_action_active(self):
        if self.workerday_details and (self.workerday_details.dttm_deleted is None) and (self.workerday_details.worker_day_id is None):
            return True
        return False



class NotificationManager(models.Manager):
    def mm_filter(self, *args, **kwargs):
        return self.filter(*args, **kwargs).select_related(
            'event',
            'event__workerday_details',
            'event__workerday_details__work_type',
            'event__workerday_details__work_type__shop'
        )




class Notifications(models.Model):
    class Meta(object):
        verbose_name = 'Уведомления'

    def __str__(self):
        return '{}, {}, {}, id: {}'.format(
            self.to_worker.last_name,
            self.to_worker.shop.title,
            self.dttm_added,
            # self.text[:60],
            self.id
        )

    id = models.BigAutoField(primary_key=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    to_worker = models.ForeignKey(User, on_delete=models.PROTECT)

    was_read = models.BooleanField(default=False)
    event = models.ForeignKey(Event, on_delete=models.PROTECT, null=True)

    # text = models.CharField(max_length=512)
    # type = models.CharField(max_length=1, choices=TYPES, default=TYPE_SUCCESS)

    # content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True)
    # object_id = models.PositiveIntegerField(blank=True, null=True)
    # object = GenericForeignKey(ct_field='content_type', fk_field='object_id')
    objects = NotificationManager()


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
        verbose_name = 'Расписание'
        verbose_name_plural = 'Расписания'

    class Status(utils.Enum):
        READY = 1
        PROCESSING = 2
        ERROR = 3

    def __str__(self):
        return 'id: {}, shop: {}, status: {}'.format(
            self.id,
            self.shop,
            self.status
        )

    id = models.BigAutoField(primary_key=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='timetable')
    status_message = models.CharField(max_length=256, null=True, blank=True)
    dt = models.DateField()
    status = utils.EnumField(Status)
    dttm_status_change = models.DateTimeField()

    # statistics
    fot = models.IntegerField(default=0, blank=True, null=True)
    lack = models.SmallIntegerField(default=0, blank=True, null=True)
    idle = models.SmallIntegerField(default=0, blank=True, null=True)
    workers_amount = models.IntegerField(default=0, blank=True, null=True)
    revenue = models.IntegerField(default=0, blank=True, null=True)
    fot_revenue = models.IntegerField(default=0, blank=True, null=True)

    task_id = models.CharField(max_length=256, null=True, blank=True)


class ProductionMonth(models.Model):
    """
    производственный календарь

    """
    class Meta(object):
        verbose_name = 'Производственный календарь'
        ordering = ('dt_first',)

    dt_first = models.DateField()
    total_days = models.SmallIntegerField()
    norm_work_days = models.SmallIntegerField()
    norm_work_hours = models.FloatField()


class ProductionDay(models.Model):
    """
    день из производственного календаря короч.

    """
    class Meta(object):
        verbose_name = 'День производственного календаря'


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
    class Meta(object):
        verbose_name = 'Статистика по рабоче сотрудника за месяц'

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    month = models.ForeignKey(ProductionMonth, on_delete=models.PROTECT)

    work_days = models.SmallIntegerField()
    work_hours = models.FloatField()


class CameraCashbox(models.Model):
    class Meta(object):
        verbose_name = 'Камеры-кассы'

    name = models.CharField(max_length=64)
    cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self):
        return '{}, {}, {}'.format(self.name, self.cashbox, self.id)


class CameraCashboxStat(models.Model):
    class Meta(object):
        verbose_name = 'Статистика по модели камера-касса'

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


class AttendanceRecords(models.Model):
    class Meta(object):
        verbose_name = 'Данные УРВ'

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
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    verified = models.BooleanField(default=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT) # todo: or should be to shop? fucking logic

    def __str__(self):
        return 'UserId: {}, type: {}, dttm: {}'.format(self.user_id, self.type, self.dttm)


class ExchangeSettings(models.Model):
    #Создаем ли автоматически вакансии
    automatic_check_lack = models.BooleanField(default=False)
    #Период, за который проверяем
    automatic_check_lack_timegap = models.DurationField(default=datetime.timedelta(days=7))

    # Минимальная потребность в сотруднике при создании вакансии
    automatic_create_vacancy_lack_min = models.FloatField(default=.5)
    # Максимальная потребность в сотруднике для удалении вакансии
    automatic_delete_vacancy_lack_max = models.FloatField(default=0.3)

    #Только автоназначение сотрудников
    automatic_worker_select_timegap = models.DurationField(default=datetime.timedelta(days=1))
    # Дробное число, на какую долю сотрудник не занят, чтобы совершить обмен
    automatic_worker_select_overflow_min = models.FloatField(default=0.8)

    #Длина смены
    working_shift_min_hours = models.DurationField(default=datetime.timedelta(hours=4)) # Минимальная длина смены
    working_shift_max_hours = models.DurationField(default=datetime.timedelta(hours=12)) # Максимальная длина смены

    automatic_worker_select_tree_level = models.IntegerField(default=1)
