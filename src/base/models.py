from django.db import models
from django.contrib.auth.models import (
    AbstractUser as DjangoAbstractUser,
)
from timezone_field import TimeZoneField

import datetime

from mptt.models import MPTTModel, TreeForeignKey


class Region(models.Model):
    class Meta:
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'
    name = models.CharField(max_length=50)
    code = models.SmallIntegerField()


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
    timezone = TimeZoneField(default='Europe/Moscow')

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

    region = models.ForeignKey(Region, on_delete=models.PROTECT, null=True)
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
        if self.is_ancestor_of(shop) or self.is_descendant_of(shop):
                return shop.level - self.level
        return None

    def get_ancestor_by_level_distance(self, level):
        if self.level == 0 or level == 0:
            return self
        level = self.level - level if self.level > level else 0
        return self.get_ancestors().filter(level=level)[0]


class EmploymentManager(models.Manager):
    def get_active(self, dt_from, dt_to, *args, **kwargs):
        """
        hired earlier then dt_from, hired later then dt_to
        :param dt_from:
        :param dt_to:
        :param args:
        :param kwargs:
        :return:
        """

        return self.filter(
            models.Q(dt_hired__lte=dt_to) | models.Q(dt_hired__isnull=True),
            models.Q(dt_fired__gte=dt_from) | models.Q(dt_fired__isnull=True),
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


class ProductionDay(models.Model):
    """
    день из производственного календаря короч.

    """
    class Meta(object):
        verbose_name = 'День производственного календаря'
        unique_together = ('dt', 'region')


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

    dt = models.DateField()
    type = models.CharField(max_length=1, choices=TYPES)
    is_celebration = models.BooleanField(default=False)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, null=True)

    def __str__(self):

        for tp in self.TYPES:
            if tp[0] == self.type:
                break
        else:
            tp = ('', 'bad_bal')

        return '(dt {}, type {}, id {})'.format(self.dt, self.type, self.id)


class User(DjangoAbstractUser):

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        # if self.shop and self.shop.parent:
        #     ss_title = self.shop.parent.title
        # else:
        #     ss_title = None
        return '{}, {}, {}'.format(self.first_name, self.last_name, self.id)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_fio(self):
        return self.last_name + ' ' + self.first_name

    id = models.BigAutoField(primary_key=True)
    middle_name = models.CharField(max_length=64, blank=True, null=True)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

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
    phone_number = models.CharField(max_length=32, null=True, blank=True)
    access_token = models.CharField(max_length=64, blank=True, null=True)

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

class Employment(models.Model):

    class Meta:
        verbose_name = 'Трудоустройство'
        verbose_name_plural = 'Трудоустройства'

    def __str__(self):
        return '{}, {}, {}'.format(self.id, self.shop, self.user)

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="employments")
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name="employments")
    function_group = models.ForeignKey(Group, on_delete=models.PROTECT, blank=True, null=True)
    position = models.ForeignKey(WorkerPosition, null=True, blank=True, on_delete=models.PROTECT)
    is_fixed_hours = models.BooleanField(default=False)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    dt_hired = models.DateField(default=datetime.date(2019, 1, 1))
    dt_fired = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # new worker restrictions
    week_availability = models.SmallIntegerField(default=7)
    norm_work_hours = models.SmallIntegerField(default=100)
    shift_hours_length_min = models.SmallIntegerField(blank=True, null=True)
    shift_hours_length_max = models.SmallIntegerField(blank=True, null=True)
    min_time_btw_shifts = models.SmallIntegerField(blank=True, null=True)

    auto_timetable = models.BooleanField(default=True)

    tabel_code = models.CharField(max_length=15, null=True, blank=True)
    is_ready_for_overworkings = models.BooleanField(default=False)

    dt_new_week_availability_from = models.DateField(null=True, blank=True)

    objects = EmploymentManager()


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
        'signout',
        'password_edit',

        'get_worker_day_approves',
        'create_worker_day_approve',
        'delete_worker_day_approve',

        'get_cashboxes',
        'get_cashboxes_info',
        # 'get_cashboxes_open_time',
        # 'get_cashboxes_used_resource',
        'create_cashbox',
        'update_cashbox',
        'delete_cashbox',

        'get_types',
        'create_work_type',
        'edit_work_type',
        'delete_work_type',

        'get_notifications',
        'get_notifications2',
        'set_notifications_read',


        'get_worker_day',
        'delete_worker_day',
        'request_worker_day',
        'set_worker_day',
        'handle_worker_day_request',
        'get_worker_day_logs',

        'get_cashier_info',
        'change_cashier_info',
        'create_cashier',
        'get_cashiers_info',

        'select_cashiers',
        'get_not_working_cashiers_list',
        'get_cashiers_list',
        'change_cashier_status',
        'set_selected_cashiers',
        'delete_cashier',

        'set_timetable',
        'create_timetable',
        'delete_timetable',
        'get_cashier_timetable',
        'get_cashiers_timetable',
        'dublicate_cashier_table',

        'get_slots',
        'get_all_slots',

        'get_workers',
        'get_outsource_workers',

        'get_user_urv',
        'upload_urv',

        'get_forecast',

        'upload_demand',
        'upload_timetable',

        'notify_workers_about_vacancy',
        'do_notify_action',

        'get_workers_to_exchange',
        'exchange_workers_day',

        #algo callbacks
        'set_demand',
        'set_pred_bills',


        'get_operation_templates',
        'create_operation_template',
        'update_operation_template',
        'delete_operation_template',

        'show_vacancy',
        'cancel_vacancy',
        'confirm_vacancy',

        # download/
        'get_demand_xlsx',
        'get_department_stats_xlsx',
        'get_timetable_xlsx',
        'get_urv_xlsx',
        'get_tabel',

        # shop/
        'get_department',
        'add_department',
        'edit_department',
        'get_department_list',
        'get_department_stats',
        'get_parameters',
        'set_parameters',

        'get_demand_change_logs',
        'get_table',

        'get_status',
        'get_change_request',
        'get_month_stat',
        'get_indicators',
        'get_worker_position_list',
        'set_worker_restrictions',
        'create_predbills_request',
    )

    METHODS = (
        'GET',
        'POST',
        'PUT',
        'DELETE'
    )

    FUNCS_TUPLE = ((f, f) for f in FUNCS)

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_modified = models.DateTimeField(blank=True, null=True)
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name='allowed_functions', blank=True, null=True)
    func = models.CharField(max_length=128, choices=FUNCS_TUPLE)
    method = models.CharField(max_length=6, choices=((m,m) for m in METHODS), default='GET')
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
