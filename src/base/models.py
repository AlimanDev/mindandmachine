import datetime
import json

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import (
    AbstractUser as DjangoAbstractUser,
)
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Case, When, Sum, Value, IntegerField, Subquery, OuterRef, F
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from model_utils import FieldTracker
from mptt.models import MPTTModel, TreeForeignKey
from timezone_field import TimeZoneField

from src.base.exceptions import MessageError
from src.base.models_abstract import AbstractActiveModel, AbstractModel, AbstractActiveNamedModel
from src.conf.djconfig import QOS_TIME_FORMAT


class Network(AbstractActiveModel):
    class Meta:
        verbose_name = 'Сеть магазинов'
        verbose_name_plural = 'Сети магазинов'

    logo = models.ImageField(null=True, blank=True, upload_to='logo/%Y/%m')
    url = models.CharField(blank=True, null=True, max_length=255)
    primary_color = models.CharField(max_length=7, blank=True)
    secondary_color = models.CharField(max_length=7, blank=True)
    name = models.CharField(max_length=128, unique=True)
    code = models.CharField(max_length=64, unique=True, null=True, blank=True)
    # нужен ли идентификатор сотруднка чтобы откликнуться на вакансию
    need_symbol_for_vacancy = models.BooleanField(default=False)
    settings_values = models.TextField(default='{}')  # настройки для сети. Cейчас есть настройки для приемки чеков + ночные смены
    allowed_interval_for_late_arrival = models.DurationField(
        verbose_name='Допустимый интервал для опоздания', default=datetime.timedelta(seconds=0))
    allowed_interval_for_early_departure = models.DurationField(
        verbose_name='Допустимый интервал для раннего ухода', default=datetime.timedelta(seconds=0))
    okpo = models.CharField(blank=True, null=True, max_length=15, verbose_name='Код по ОКПО')
    allowed_geo_distance_km = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='Разрешенная дистанция до магазина при создании отметок (км)',
    )
    enable_camera_ticks = models.BooleanField(
        default=False, verbose_name='Включить отметки по камере в мобильной версии')

    def get_department(self):
        return None

    @cached_property
    def night_edges(self):
        default_night_edges = (
            '22:00:00',
            '06:00:00',
        )
        return json.loads(self.settings_values).get('night_edges', default_night_edges)

    def __str__(self):
        return f'name: {self.name}, code: {self.code}'


class Region(AbstractActiveNamedModel):
    class Meta(AbstractActiveNamedModel.Meta):
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'


class Break(AbstractActiveNamedModel):
    class Meta(AbstractActiveNamedModel.Meta):
        verbose_name = 'Перерыв'
        verbose_name_plural = 'Перерывы'
    value = models.CharField(max_length=1024, default='[]')

    def __getattribute__(self, attr):
        if attr in ['breaks']:
            try:
                return super().__getattribute__(attr)
            except:
                try:
                    self.__setattr__(attr, json.loads(self.value))
                except:
                    return []
        return super().__getattribute__(attr)

    @classmethod
    def get_break_triplets(cls, network_id):
        return {
            b.id: list(map(lambda x: (x[0] * 60, x[1] * 60, sum(x[2]) * 60), b.breaks))
            for b in cls.objects.filter(network_id=network_id)
        }

    @staticmethod
    def clean_value(value):
        return json.dumps(value)

    def save(self, *args, **kwargs):
        self.value = self.clean_value(self.breaks)
        return super().save(*args, **kwargs)


class ShopSettings(AbstractActiveNamedModel):
    class Meta(AbstractActiveNamedModel.Meta):
        verbose_name = 'Настройки автосоставления'
        verbose_name_plural = 'Настройки автосоставления'

    PRODUCTION_CAL = 'P'
    YEAR_NORM = 'N'

    PROCESS_TYPE = (
        (PRODUCTION_CAL, 'production calendar'),
        (YEAR_NORM, 'norm per year')
    )
    # json fields
    method_params = models.CharField(max_length=4096, default='[]')
    cost_weights = models.CharField(max_length=4096, default='{}')
    init_params = models.CharField(max_length=2048, default='{"n_working_days_optimal": 20}')
    breaks = models.ForeignKey(Break, on_delete=models.PROTECT)

    # added on 21.12.2018
    idle = models.SmallIntegerField(default=0)  # percents
    fot = models.IntegerField(default=0)
    less_norm = models.SmallIntegerField(default=0)  # percents
    more_norm = models.SmallIntegerField(default=0)  # percents
    shift_start = models.SmallIntegerField(default=6)
    shift_end = models.SmallIntegerField(default=12)
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

    def get_department(self):
        return None


# на самом деле это отдел
class Shop(MPTTModel, AbstractActiveNamedModel):
    class Meta:
        # unique_together = ('parent', 'title')
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'

    LOAD_TEMPLATE_PROCESS = 'P'
    LOAD_TEMPLATE_READY = 'R'
    LOAD_TEMPLATE_ERROR = 'E'

    LOAD_TEMPLATE_STATUSES = [
        (LOAD_TEMPLATE_PROCESS, 'В процессе'),
        (LOAD_TEMPLATE_READY, 'Готово'),
        (LOAD_TEMPLATE_ERROR, 'Ошибка'),
    ]

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

    code = models.CharField(max_length=64, null=True, blank=True)
    # From supershop
    address = models.CharField(max_length=256, blank=True, null=True)
    type = models.CharField(max_length=1, choices=DEPARTMENT_TYPES, default=TYPE_SHOP)

    dt_opened = models.DateField(null=True, blank=True)
    dt_closed = models.DateField(null=True, blank=True)

    mean_queue_length = models.FloatField(default=3)
    max_queue_length = models.FloatField(default=7)
    dead_time_part = models.FloatField(default=0.1)

    beta = models.FloatField(default=0.9)  # for creating timetable, (a function from previous 3 variables)

    demand_coef = models.FloatField(default=1)  # unknown trend for algorithm

    forecast_step_minutes = models.TimeField(default=datetime.time(minute=30))
    # man_presence = models.FloatField(default=0)

    count_lack = models.BooleanField(default=False)

    tm_open_dict = models.TextField(default='{}')
    tm_close_dict = models.TextField(default='{}')
    area = models.FloatField(default=0)  # Торговая площадь магазина

    restricted_start_times = models.CharField(max_length=1024, default='[]')
    restricted_end_times = models.CharField(max_length=1024, default='[]')

    load_template = models.ForeignKey('forecast.LoadTemplate', on_delete=models.SET_NULL, null=True, related_name='shops', blank=True)
    load_template_status = models.CharField(max_length=1, default=LOAD_TEMPLATE_READY, choices=LOAD_TEMPLATE_STATUSES)
    exchange_settings = models.ForeignKey('timetable.ExchangeSettings', on_delete=models.SET_NULL, null=True, related_name='shops', blank=True)

    staff_number = models.SmallIntegerField(default=0)

    region = models.ForeignKey(Region, on_delete=models.PROTECT)

    email = models.EmailField(blank=True, null=True)
    exchange_shops = models.ManyToManyField('self', blank=True)

    settings = models.ForeignKey(ShopSettings, on_delete=models.PROTECT, null=True, blank=True)

    latitude = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, verbose_name='Широта')
    longitude = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True, verbose_name='Долгота')
    director = models.ForeignKey('base.User', null=True, blank=True, verbose_name='Директор', on_delete=models.SET_NULL)

    def __str__(self):
        return '{}, {}, {}'.format(
            self.name,
            self.parent_title(),
            self.id)

    def system_step_in_minutes(self):
        return self.forecast_step_minutes.hour * 60 + self.forecast_step_minutes.minute

    def parent_title(self):
        return self.parent.name if self.parent else '',

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

    def get_department(self):
        return self

    def __init__(self, *args, **kwargs):
        parent_code = kwargs.pop('parent_code', None)
        super().__init__(*args, **kwargs)
        if parent_code:
            self.parent = get_object_or_404(Shop, code=parent_code)

    @property
    def director_code(self):
        return getattr(self.director, 'tabel_code', None)

    @director_code.setter
    def director_code(self, val):
        self.director = User.objects.filter(tabel_code=val).first()

    def __getattribute__(self, attr):
        if attr in ['open_times', 'close_times']:
            try:
                return super().__getattribute__(attr)
            except:
                fields_scope = {
                    'open_times': 'tm_open_dict',
                    'close_times': 'tm_close_dict',
                }
                try:
                    self.__setattr__(attr, {
                        k: datetime.datetime.strptime(v, QOS_TIME_FORMAT).time()
                        for k, v in json.loads(getattr(self, fields_scope.get(attr))).items()
                    })
                except:
                    return {}
        return super().__getattribute__(attr)

    @staticmethod
    def clean_time_dict(time_dict):
        new_dict = dict(time_dict)
        dict_keys = list(new_dict.keys())
        for key in dict_keys:
            if 'd' in key:
                new_dict[key.replace('d', '')] = new_dict.pop(key)
        return json.dumps(new_dict, cls=DjangoJSONEncoder)  # todo: actually values should be time object, so  django json serializer should be used

    def save(self, *args, **kwargs):
        open_times = self.open_times
        close_times = self.close_times
        if open_times.keys() != close_times.keys():
            raise MessageError(code='time_shop_differerent_keys')
        if open_times.get('all') and len(open_times) != 1:
            raise MessageError(code='time_shop_all_or_days')
        
        #TODO fix
        # for key in open_times.keys():
        #     close_hour = close_times[key].hour if close_times[key].hour != 0 else 24
        #     if open_times[key].hour > close_hour:
        #         raise MessageError(code='time_shop_incorrect_time_start_end')
        self.tm_open_dict = self.clean_time_dict(self.open_times)
        self.tm_close_dict = self.clean_time_dict(self.close_times)
        if hasattr(self, 'parent_code'):
            self.parent = get_object_or_404(Shop, code=self.parent_code)
        load_template = None
        if self.load_template_id and self.id:
            new_template = self.load_template_id
            self.refresh_from_db(fields=['load_template_id'])
            load_template = self.load_template_id
            self.load_template_id = new_template
        super().save(*args, **kwargs)
        if False: # self.load_template_id:  # aa: todo: fixme: delete tmp False
            from src.forecast.load_template.utils import apply_load_template
            if load_template != None and load_template != new_template:
                apply_load_template(new_template, self.id)
            elif load_template == None:
                apply_load_template(self.load_template_id, self.id)

    def get_exchange_settings(self):
        return self.exchange_settings if self.exchange_settings_id \
            else apps.get_model(
                'timetable',
                'ExchangeSettings',
            ).objects.filter(
                network_id=self.network_id,
                shops__isnull=True,
            ).first()

    def get_tz_offset(self):
        if self.timezone:
            offset = int(self.timezone.utcoffset(datetime.datetime.now()).seconds / 3600)
        else:
            offset = settings.CLIENT_TIMEZONE

        return offset

class EmploymentManager(models.Manager):
    def get_active(self, network_id, dt_from=None, dt_to=None, *args, **kwargs):
        """
        hired earlier then dt_from, hired later then dt_to
        :paramShop dt_from:
        :param dt_to:
        :param args:
        :param kwargs:
        :return:
        """
        today = datetime.date.today()
        dt_from = dt_from or today
        dt_to = dt_to or today

        return self.filter(
            models.Q(dt_hired__lte=dt_to) | models.Q(dt_hired__isnull=True),
            models.Q(dt_fired__gte=dt_from) | models.Q(dt_fired__isnull=True),
            shop__network_id=network_id,
            user__network_id=network_id
        ).filter(*args, **kwargs)


class Group(AbstractActiveNamedModel):
    class Meta(AbstractActiveNamedModel.Meta):
        verbose_name = 'Группа пользователей'
        verbose_name_plural = 'Группы пользователей'

    dttm_modified = models.DateTimeField(blank=True, null=True)
    subordinates = models.ManyToManyField("self", blank=True)

    def __str__(self):
        return '{}, {}, {}'.format(
            self.id,
            self.name,
            self.subordinates.all() if self.subordinates.all() else ''
        )


class ProductionDay(AbstractModel):
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

    @classmethod
    def get_norm_work_hours(cls, region_id, month, year):
        norm_work_hours = ProductionDay.objects.filter(
            dt__month=month,
            dt__year=year,
            type__in=ProductionDay.WORK_TYPES,
            region_id=region_id,
        ).annotate(
            work_hours=Case(
                When(type=ProductionDay.TYPE_WORK, then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK])),
                When(type=ProductionDay.TYPE_SHORT_WORK,
                     then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_SHORT_WORK])),
            )
        ).aggregate(
            norm_work_hours=Sum('work_hours', output_field=IntegerField())
        )['norm_work_hours']
        return norm_work_hours


class User(DjangoAbstractUser, AbstractModel):
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
    tabel_code = models.CharField(blank=True, max_length=64, null=True, unique=True)
    lang = models.CharField(max_length=2, default='ru')
    network = models.ForeignKey(Network, on_delete=models.PROTECT, null=True)
    black_list_symbol = models.CharField(max_length=128, null=True, blank=True)

    def get_fio(self):
        """
        :return: Фамилия Имя Отчество (если есть)
        """
        fio = f'{self.last_name} {self.first_name}'
        if self.middle_name:
            fio += f' {self.middle_name}'
        return fio

    def get_short_fio(self):
        """
        :return: Фамилия с инициалами
        """
        short_fio = f'{self.last_name} {self.first_name[0].upper()}.'
        if self.middle_name:
            short_fio += f'{self.middle_name[0].upper()}.'
        return short_fio

    @property
    def short_fio(self):
        return self.get_short_fio()

    @property
    def fio(self):
        return self.get_fio()

    def get_active_employments(self, network, shop=None):
        kwargs = {'network_id': network.id}
        if shop:
            kwargs['shop__in'] = shop.get_ancestors(include_self=True)
        return self.employments.get_active(**kwargs)

    def get_group_ids(self, network, shop=None):
        return self.get_active_employments(network, shop).annotate(
            group_id=Coalesce(F('function_group_id'), F('position__group_id')),
        ).values_list('group_id', flat=True)


class WorkerPosition(AbstractActiveNamedModel):
    """
    Describe employee's position
    """

    class Meta(AbstractActiveNamedModel.Meta):
        verbose_name = 'Должность сотрудника'
        verbose_name_plural = 'Должности сотрудников'

    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(Group, on_delete=models.PROTECT, blank=True, null=True)
    default_work_type_names = models.ManyToManyField(
        to='timetable.WorkTypeName',
        verbose_name='Типы работ по умолчанию',
        blank=True,
    )
    breaks = models.ForeignKey(Break, on_delete=models.PROTECT, null=True, blank=True)

    def __str__(self):
        return '{}, {}'.format(self.name, self.id)

    def get_department(self):
        return None


class EmploymentQuerySet(QuerySet):
    def last_hired(self):
        last_hired_subq = self.filter(user_id=OuterRef('user_id')).order_by('-dt_hired').values('id')[:1]
        return self.filter(
            id=Subquery(last_hired_subq)
        )


class Employment(AbstractActiveModel):
    class Meta:
        verbose_name = 'Трудоустройство'
        verbose_name_plural = 'Трудоустройства'
        unique_together = (
            ('code', 'network'),
        )

    def __str__(self):
        return '{}, {}, {}'.format(self.id, self.shop, self.user)

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=128, null=True, blank=True)
    network = models.ForeignKey('base.Network', on_delete=models.PROTECT, null=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="employments")
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name="employments")
    function_group = models.ForeignKey(Group, on_delete=models.PROTECT, blank=True, null=True)
    position = models.ForeignKey(WorkerPosition, null=True, blank=True, on_delete=models.PROTECT)
    is_fixed_hours = models.BooleanField(default=False)

    dt_hired = models.DateField(default=datetime.date(2019, 1, 1))
    dt_hired_next = models.DateField(null=True, blank=True)  # todo: удалить поле, временное для интеграции из-за того, что не поддерживаем несколько трудоустройств в течение месяца
    # Сотрудник может на несколько недель уйти поработать в другой магазин и вернуться. Официально как временный перевод могут оформить
    dt_fired = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # new worker restrictions
    week_availability = models.SmallIntegerField(default=7)
    norm_work_hours = models.SmallIntegerField(default=100)
    shift_hours_length_min = models.SmallIntegerField(blank=True, null=True)
    shift_hours_length_max = models.SmallIntegerField(blank=True, null=True)
    min_time_btw_shifts = models.SmallIntegerField(blank=True, null=True)

    auto_timetable = models.BooleanField(default=True)

    tabel_code = models.CharField(max_length=64, null=True, blank=True)
    is_ready_for_overworkings = models.BooleanField(default=False)

    dt_new_week_availability_from = models.DateField(null=True, blank=True)
    is_visible = models.BooleanField(default=True)

    position_tracker = FieldTracker(fields=['position'])

    objects = EmploymentManager.from_queryset(EmploymentQuerySet)()

    def has_permission(self, permission, method='GET'):
        group = self.function_group or (self.position.group if self.position else None)
        if not group:
            raise MessageError(code='no_group_or_position')
        return group.allowed_functions.filter(
            func=permission,
            method=method
        ).first()

    def get_department(self):
        return self.shop

    def get_short_fio_and_position(self):
        short_fio_and_position = f'{self.user.get_short_fio()}'
        if self.position and self.position.name:
            short_fio_and_position += f', {self.position.name}'

        return short_fio_and_position

    def __init__(self, *args, **kwargs):
        shop_code = kwargs.pop('shop_code', None)
        username = kwargs.get('username', None)
        user_id = kwargs.get('user_id', None)
        position_code = kwargs.pop('position_code', None)
        super().__init__(*args, **kwargs)
        if shop_code:
            self.shop = Shop.objects.get(code=shop_code)
        if username and not user_id:
            self.user = User.objects.get(username=username)
            self.user_id = self.user.id

        if position_code:
            self.position = WorkerPosition.objects.get(code=position_code)

    def save(self, *args, **kwargs):
        if hasattr(self, 'shop_code'):
            self.shop = Shop.objects.get(code=self.shop_code)
        if hasattr(self, 'username'):
            self.user = User.objects.get(username=self.username)
        if hasattr(self, 'position_code'):
            self.position = WorkerPosition.objects.get(code=self.position_code)

        force_create_work_types = kwargs.pop('force_create_work_types', False)
        is_new = self.pk is None
        position_has_changed = self.position_tracker.has_changed('position')
        res = super().save(*args, **kwargs)
        # при создании трудоустройства или при смене должности проставляем типы работ по умолчанию
        if force_create_work_types or is_new or position_has_changed:
            from src.timetable.models import EmploymentWorkType, WorkType
            work_type_names = WorkerPosition.default_work_type_names.through.objects.filter(
                workerposition_id=self.position_id,
            ).values_list('worktypename', flat=True)

            work_types = []
            for work_type_name_id in work_type_names:
                work_type, _wt_created = WorkType.objects.get_or_create(
                    shop_id=self.shop_id,
                    work_type_name_id=work_type_name_id,
                )
                work_types.append(work_type)

            if work_types or not is_new:
                EmploymentWorkType.objects.filter(employment_id=self.id).delete()

            if work_types:
                EmploymentWorkType.objects.bulk_create(
                    EmploymentWorkType(
                        employment_id=self.id,
                        work_type=work_type,
                        priority=1,
                    ) for work_type in work_types
                )
        # при смене должности пересчитываем рабочие часы в будущем
        if position_has_changed:
            from django.apps import apps
            from django.db.models import When, Case, Q, F, DurationField, Value, Subquery, OuterRef
            from django.db.models.functions import Cast, Coalesce
            if self.position.breaks:
                break_id = self.position.breaks_id
                breaks = self.position.breaks.breaks
            else:
                break_id = self.shop.settings.breaks_id
                breaks = self.shop.settings.breaks.breaks
            breaks = list(
                map(
                    lambda x: (
                        datetime.timedelta(seconds=x[0] * 60), 
                        datetime.timedelta(seconds=x[1] * 60), 
                        datetime.timedelta(seconds=sum(x[2]) * 60)
                    ), 
                    breaks
                )
            )
            breaktime_plan = Value(datetime.timedelta(0), output_field=DurationField())
            if len(breaks):
                whens = [
                    When(
                        Q(hours_plan_0__gte=break_triplet[0], hours_plan_0__lte=break_triplet[1]) & 
                        (Q(employment__position__breaks_id=break_id) | 
                        (Q(employment__position__breaks__isnull=True) & Q(employment__shop__settings__breaks_id=break_id))),
                        then=break_triplet[2]
                    )
                    for break_triplet in breaks
                ]
                breaktime_plan = Case(*whens, output_field=DurationField())
            WorkerDay = apps.get_model('timetable', 'WorkerDay')
            dt = datetime.date.today()
            WorkerDay.objects.filter(
                employment_id=self.id,
                is_fact=False,
                dt__gt=dt,
            ).update(
                work_hours=Coalesce(Subquery(
                    WorkerDay.objects.filter(pk=OuterRef('pk')).annotate(
                        hours_plan_0=Cast(F('dttm_work_end') - F('dttm_work_start'), DurationField()),
                        hours_plan=Cast(F('hours_plan_0') - breaktime_plan, DurationField()),
                    ).values('hours_plan')[:1]
                ), datetime.timedelta(0))
            )

        return res


class FunctionGroup(AbstractModel):
    class Meta:
        verbose_name = 'Доступ к функциям'
        unique_together = (('func', 'group', 'method'),)

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
        'AutoSettings_create_timetable',
        'AutoSettings_set_timetable',
        'AutoSettings_delete_timetable',
        'AuthUserView',
        'Break',
        'Employment',
        'Employment_auto_timetable',
        'EmploymentWorkType',
        'ExchangeSettings',
        'FunctionGroupView',
        'FunctionGroupView_functions',
        'LoadTemplate',
        'LoadTemplate_apply',
        'LoadTemplate_calculate',
        'Network',
        'Notification',
        'OperationTemplate',
        'OperationTypeName',
        'OperationType',
        'OperationTypeRelation',
        'OperationTypeTemplate',
        'PeriodClients',
        'PeriodClients_indicators',
        'PeriodClients_put',
        'PeriodClients_delete',
        'PeriodClients_upload',
        'PeriodClients_download',
        'Receipt',
        'Group',
        'Shop',
        'Shop_stat',
        'Shop_tree',
        'Subscribe',
        'User',
        'User_change_password',
        'WorkerConstraint',
        'WorkerDay',
        'WorkerDay_approve',
        'WorkerDay_daily_stat',
        'WorkerDay_worker_stat',
        'WorkerDay_vacancy',
        'WorkerDay_change_list',
        'WorkerDay_duplicate',
        'WorkerDay_delete_timetable',
        'WorkerDay_exchange',
        'WorkerDay_confirm_vacancy',
        'WorkerDay_upload',
        'WorkerDay_download_timetable',
        'WorkerDay_download_tabel',
        'WorkerDay_editable_vacancy',
        'WorkerDay_approve_vacancy',
        'WorkerPosition',
        'WorkTypeName',
        'WorkType',
        'WorkType_efficiency',
        'ShopMonthStat',
        'ShopMonthStat_status',
        'ShopSettings',
        'VacancyBlackList',

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

        # algo callbacks
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
    method = models.CharField(max_length=6, choices=((m, m) for m in METHODS), default='GET')
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


EVENT_TYPES = [
    ('vacancy', 'Вакансия'),
    ('timetable', 'Изменения в расписании'),
    ('load_template_err', 'Ошибка применения шаблона нагрузки'),
    ('load_template_apply', 'Шаблон нагрузки применён'),
    ('shift_elongation', 'Расширение смены'),
    ('holiday_exchange', 'Вывод с выходного'),
    ('auto_vacancy', 'Автоматическая биржа смен'),
    ('vacancy_canceled', 'Вакансия отменена'),
]


class Event(AbstractModel):
    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_valid_to = models.DateTimeField(auto_now_add=True)
    worker_day = models.ForeignKey('timetable.WorkerDay', null=True, blank=True, on_delete=models.CASCADE)

    type = models.CharField(choices=EVENT_TYPES, max_length=20)
    shop = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT, related_name="events")
    params = models.CharField(default='{}', max_length=512)


class Subscribe(AbstractActiveModel):
    type = models.CharField(choices=EVENT_TYPES, max_length=20)
    user = models.ForeignKey(User, null=False, on_delete=models.PROTECT)
    shop = models.ForeignKey(Shop, null=False, on_delete=models.PROTECT)


class Notification(AbstractModel):
    class Meta(object):
        verbose_name = 'Уведомления'

    def __str__(self):
        return '{}, {}, {}, id: {}'.format(
            self.worker,
            self.event,
            self.dttm_added,
            # self.text[:60],
            self.id
        )

    dttm_added = models.DateTimeField(auto_now_add=True)
    worker = models.ForeignKey(User, on_delete=models.PROTECT)

    is_read = models.BooleanField(default=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, null=True)
