import datetime
import json
import re
from calendar import monthrange

import pandas as pd
from celery import chain
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import (
    AbstractUser as DjangoAbstractUser,
)
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db import transaction
from django.db.models import Case, When, Sum, Value, IntegerField, Subquery, OuterRef, F
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from model_utils import FieldTracker
from mptt.models import MPTTModel, TreeForeignKey
from timezone_field import TimeZoneField

from src.base.exceptions import MessageError
from src.base.models_abstract import (
    AbstractActiveModel,
    AbstractModel,
    AbstractActiveNetworkSpecificCodeNamedModel,
    NetworkSpecificModel,
)
from src.conf.djconfig import QOS_TIME_FORMAT


class Network(AbstractActiveModel):
    ACCOUNTING_PERIOD_LENGTH_CHOICES = (
        (1, 'Месяц'),
        (3, 'Квартал'),
        (6, 'Пол года'),
        (12, 'Год'),
    )

    TABEL_FORMAT_CHOICES = (
        ('mts', 'MTSTabelGenerator'),
        ('t13_custom', 'CustomT13TabelGenerator'),
        ('aigul', 'AigulTabelGenerator'),
    )

    CONVERT_TABEL_TO_CHOICES = (
        ('xlsx', 'xlsx'),
        ('pdf', 'PDF'),
    )

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
    crop_work_hours_by_shop_schedule = models.BooleanField(
        default=False, verbose_name='Обрезать рабочие часы по времени работы магазина'
    )
    clean_wdays_on_employment_dt_change = models.BooleanField(
        default=False, verbose_name='Запускать скрипт очистки дней при изменении дат трудойстройства',
    )
    accounting_period_length = models.PositiveSmallIntegerField(
        choices=ACCOUNTING_PERIOD_LENGTH_CHOICES, verbose_name='Длина учетного периода', default=1)
    only_fact_hours_that_in_approved_plan = models.BooleanField(
        default=False,
        verbose_name='Считать только те фактические часы, которые есть в подтвержденном плановом графике',
    )
    download_tabel_template = models.CharField(
        max_length=64, verbose_name='Шаблон для табеля',
        choices=TABEL_FORMAT_CHOICES, default='mts',
    )
    convert_tabel_to = models.CharField(
        max_length=64, verbose_name='Конвертировать табель в',
        null=True, blank=True,
        choices=CONVERT_TABEL_TO_CHOICES,
        default='xlsx',
    )

    def get_department(self):
        return None

    @cached_property
    def night_edges(self):
        default_night_edges = (
            '22:00:00',
            '06:00:00',
        )
        return json.loads(self.settings_values).get('night_edges', default_night_edges)

    @cached_property
    def accounting_periods_count(self):
        return int(12 / self.accounting_period_length)

    def get_acc_period_range(self, dt):
        period_num_within_year = dt.month // self.accounting_period_length
        if dt.month % self.accounting_period_length > 0:
            period_num_within_year += 1
        end_month = period_num_within_year * self.accounting_period_length
        start_month = end_month - (self.accounting_period_length - 1)

        return datetime.date(dt.year, start_month, 1), \
            datetime.date(dt.year, end_month, monthrange(dt.year, end_month)[1])

    def __str__(self):
        return f'name: {self.name}, code: {self.code}'


class Region(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'


class Break(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
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


class ShopSettings(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
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
class Shop(MPTTModel, AbstractActiveNetworkSpecificCodeNamedModel):
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

    tracker = FieldTracker(fields=['tm_open_dict', 'tm_close_dict', 'load_template'])

    def __str__(self):
        return '{}, {}, {}, {}'.format(
            self.name,
            self.parent_title(),
            self.id,
            self.code,
        )

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

    def _parse_times(self, attr):
        return {
            k: datetime.datetime.strptime(v, QOS_TIME_FORMAT).time()
            for k, v in json.loads(getattr(self, attr)).items()
        }

    @property
    def open_times(self):
        return self._parse_times('tm_open_dict')

    @property
    def close_times(self):
        return self._parse_times('tm_close_dict')

    @staticmethod
    def clean_time_dict(time_dict):
        new_dict = dict(time_dict)
        dict_keys = list(new_dict.keys())
        for key in dict_keys:
            if 'd' in key:
                new_dict[key.replace('d', '')] = new_dict.pop(key)
        return json.dumps(new_dict, cls=DjangoJSONEncoder)  # todo: actually values should be time object, so  django json serializer should be used

    def _handle_schedule_change(self):
        from src.util.models_converter import Converter
        from src.celery.tasks import fill_shop_schedule, recalc_wdays
        dt_now = datetime.datetime.now().date()
        ch = chain(
            fill_shop_schedule.si(shop_id=self.id, dt_from=Converter.convert_date(dt_now)),
            recalc_wdays.si(
                shop_id=self.id,
                dt_from=Converter.convert_date(dt_now),
                dt_to=Converter.convert_date(dt_now + datetime.timedelta(days=90))),
        )
        ch.apply_async()

    def save(self, *args, **kwargs):
        if self.open_times.keys() != self.close_times.keys():
            raise MessageError(code='time_shop_differerent_keys')
        if self.open_times.get('all') and len(self.open_times) != 1:
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
        load_template_changed = self.tracker.has_changed('load_template')
        if load_template_changed and self.load_template_status == self.LOAD_TEMPLATE_PROCESS:
            raise MessageError(code='cant_change_load_template')
        res = super().save(*args, **kwargs)
        if self.tracker.has_changed('tm_open_dict') or self.tracker.has_changed('tm_close_dict'):
            transaction.on_commit(self._handle_schedule_change)
        if load_template_changed and not (self.load_template_id is None):
            from src.forecast.load_template.utils import apply_load_template
            from src.celery.tasks import calculate_shops_load
            apply_load_template(self.load_template_id, self.id)
            calculate_shops_load.delay(
                self.load_template_id,
                datetime.date.today(),
                datetime.date.today().replace(day=1) + relativedelta(months=1),
                shop_id=self.id,
            )

        return res

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

    def get_standard_schedule(self, dt):
        res = {}
        weekday = str(dt.weekday())

        if 'all' in self.open_times:
            res['tm_open'] = self.open_times.get('all')
        elif weekday in self.open_times:
            res['tm_open'] = self.open_times.get(weekday)

        if 'all' in self.close_times:
            res['tm_close'] = self.close_times.get('all')
        elif weekday in self.close_times:
            res['tm_close'] = self.close_times.get(weekday)

        return res or None

    def get_schedule(self, dt: datetime.date):
        return self.get_period_schedule(dt_from=dt, dt_to=dt)[dt]

    def get_period_schedule(self, dt_from: datetime.date, dt_to: datetime.date):
        res = {}

        ss_dict = {}
        for ss in ShopSchedule.objects.filter(shop=self, dt__gte=dt_from, dt__lte=dt_to):
            schedule = None
            if ss.type == ShopSchedule.WORKDAY_TYPE:
                schedule = {
                    'tm_open': ss.opens,
                    'tm_close': ss.closes,
                }
            ss_dict[ss.dt] = schedule

        for dt in pd.date_range(dt_from, dt_to):
            dt = dt.date()
            res[dt] = ss_dict.get(dt, self.get_standard_schedule(dt))

        return res

    def get_work_schedule(self, dt_from, dt_to):
        """
        Получения расписания в виде словаря (передается на алгоритмы)
        :param dt_from: дата от, включительно
        :param dt_to: дата до, включительно
        :return:
        """
        from src.util.models_converter import Converter
        work_schedule = {}
        for dt, schedule_dict in self.get_period_schedule(dt_from=dt_from, dt_to=dt_to).items():
            schedule = None  # TODO: это и "нет данных" и выходной, нормально ли?
            if schedule_dict:
                schedule = (
                    Converter.convert_time(schedule_dict['tm_open']),
                    Converter.convert_time(schedule_dict['tm_close'])
                )
            work_schedule[Converter.convert_date(dt)] = schedule
        return work_schedule

    @property
    def nonstandard_schedule(self):
        return self.shopschedule_set.filter(modified_by__isnull=False)


class EmploymentManager(models.Manager):
    def get_active(self, network_id=None, dt_from=None, dt_to=None, *args, **kwargs):
        """
        hired earlier then dt_from, hired later then dt_to
        :param network_id:
        :param dt_from:
        :param dt_to:
        :param args:
        :param kwargs:
        :return:
        """
        today = datetime.date.today()
        dt_from = dt_from or today
        dt_to = dt_to or today

        q = models.Q(
            models.Q(dt_hired__lte=dt_to) | models.Q(dt_hired__isnull=True),
            models.Q(dt_fired__gte=dt_from) | models.Q(dt_fired__isnull=True),
        )
        if network_id:
            q &= models.Q(
                shop__network_id=network_id,
                user__network_id=network_id,
            )
        qs = self.filter(q)
        return qs.filter(*args, **kwargs)

    def get_active_empl_for_user(
            self, network_id, user_id, dt=None, priority_shop_id=None, priority_employment_id=None):
        qs = self.get_active(network_id, dt_from=dt, dt_to=dt, user_id=user_id)

        order_by = []

        if priority_shop_id:
            qs = qs.annotate_value_equality(
                'is_equal_shops', 'shop_id', priority_shop_id,
            )
            order_by.append('-is_equal_shops')

        if priority_employment_id:
            qs = qs.annotate_value_equality(
                'is_equal_employments', 'id', priority_employment_id,
            )
            order_by.append('-is_equal_employments')

        if order_by:
            qs = qs.order_by(*order_by)

        return qs


class Group(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
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
    def get_norm_work_hours(cls, region_id, year, month=None):
        """
        Получение нормы часов по производственному календарю для региона.
        Если не указывать месяц, то вернется словарь с часами для всех месяцев года.
        :param region_id:
        :param year:
        :param month:
        :return: Словарь, где ключ - номер месяца, значение - количество часов.
        """
        filter_kwargs = dict(
            dt__year=year,
            type__in=ProductionDay.WORK_TYPES,
            region_id=region_id,
        )
        if month:
            filter_kwargs['dt__month'] = month

        norm_work_hours = ProductionDay.objects.filter(
            **filter_kwargs
        ).annotate(
            work_hours=Case(
                When(type=ProductionDay.TYPE_WORK, then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK])),
                When(type=ProductionDay.TYPE_SHORT_WORK,
                     then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_SHORT_WORK])),
            )
        ).values(
            'dt__month',
        ).annotate(
            norm_work_hours=Sum('work_hours', output_field=IntegerField())
        ).values_list('dt__month', 'norm_work_hours')
        return dict(norm_work_hours)


class User(DjangoAbstractUser, AbstractModel):
    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        # if self.shop and self.shop.parent:
        #     ss_title = self.shop.parent.title
        # else:
        #     ss_title = None
        return '{}, {}, {}, {}'.format(self.first_name, self.last_name, self.id, self.username)

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


class WorkerPosition(AbstractActiveNetworkSpecificCodeNamedModel):
    """
    Describe employee's position
    """

    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
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
    hours_in_a_week = models.PositiveSmallIntegerField(default=40, verbose_name='Часов в рабочей неделе')

    def __str__(self):
        return '{}, {}'.format(self.name, self.id)

    @cached_property
    def wp_defaults(self):
        wp_defaults_dict = settings.WORKER_POSITION_DEFAULT_VALUES.get(self.network.code)
        if wp_defaults_dict:
            for re_pattern, wp_defaults in wp_defaults_dict.items():
                if re.search(re_pattern, self.name, re.IGNORECASE):
                    return wp_defaults

    def _set_plain_defaults(self):
        if self.wp_defaults:
            hours_in_a_week = self.wp_defaults.get('hours_in_a_week')
            if hours_in_a_week:
                self.hours_in_a_week = hours_in_a_week
            breaks_code = self.wp_defaults.get('breaks_code')
            if breaks_code:
                self.breaks = Break.objects.filter(network_id=self.network_id, code=breaks_code).first()
            group_code = self.wp_defaults.get('group_code')
            if group_code:
                self.group = Group.objects.filter(network_id=self.network_id, code=group_code).first()

    def _set_m2m_defaults(self):
        if self.wp_defaults:
            default_work_type_names_codes = self.wp_defaults.get('default_work_type_names_codes')
            if default_work_type_names_codes:
                from src.timetable.models import WorkTypeName
                self.default_work_type_names.set(
                    WorkTypeName.objects.filter(network=self.network, code__in=default_work_type_names_codes))

    def save(self, *args, **kwargs):
        is_new = self.id is None
        if is_new:
            self._set_plain_defaults()
        res = super(WorkerPosition, self).save(*args, **kwargs)
        if is_new:
            self._set_m2m_defaults()
        return res

    def get_department(self):
        return None


class EmploymentQuerySet(QuerySet):
    def annotate_value_equality(self, annotate_name, field_name, value):
        return self.annotate(**{annotate_name: Case(
            When(**{field_name: value}, then=True),
            default=False, output_field=models.BooleanField()
        )})

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
    function_group = models.ForeignKey(Group, on_delete=models.PROTECT, blank=True, null=True, related_name="employments")
    dt_to_function_group = models.DateField(verbose_name='Дата до которой действуют права function_group', null=True, blank=True)
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

    tracker = FieldTracker(fields=['position', 'dt_hired', 'dt_fired'])

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
        position_has_changed = self.tracker.has_changed('position')
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
        if not is_new and position_has_changed:
            from src.timetable.models import WorkerDay
            dt = datetime.date.today()
            for wd in WorkerDay.objects.filter(
                        employment_id=self.id,
                        is_fact=False,
                        dt__gt=dt,
                        type__in=WorkerDay.TYPES_WITH_TM_RANGE,
                    ):
                wd.save()

        if (is_new or (self.tracker.has_changed('dt_hired') or self.tracker.has_changed('dt_fired'))) and \
                self.network and self.network.clean_wdays_on_employment_dt_change:
            from src.celery.tasks import clean_wdays
            from src.timetable.models import WorkerDay
            from src.util.models_converter import Converter
            kwargs = {
                'only_logging': False,
                'clean_plan_empl': True,
            }
            if is_new:
                kwargs['filter_kwargs'] = {
                    'type': WorkerDay.TYPE_WORKDAY,
                    'worker_id': self.user_id,
                }
                if self.dt_hired:
                    kwargs['filter_kwargs']['dt__gte'] = Converter.convert_date(self.dt_hired)
                if self.dt_fired:
                    kwargs['filter_kwargs']['dt__lt'] = Converter.convert_date(self.dt_fired)
            else:
                prev_dt_hired = self.tracker.previous('dt_hired')
                if prev_dt_hired and prev_dt_hired < self.dt_hired:
                    dt__gte = prev_dt_hired
                else:
                    dt__gte = self.dt_hired
                kwargs['filter_kwargs'] = {
                    'type': WorkerDay.TYPE_WORKDAY,
                    'worker_id': self.user_id,
                    'dt__gte': Converter.convert_date(dt__gte),
                }

            clean_wdays.apply_async(kwargs=kwargs)

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
        'Employment_timetable',
        'EmploymentWorkType',
        'ExchangeSettings',
        'FunctionGroupView',
        'FunctionGroupView_functions',
        'LoadTemplate',
        'LoadTemplate_apply',
        'LoadTemplate_calculate',
        'LoadTemplate_download',
        'LoadTemplate_upload',
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
        'WorkerDay_copy_approved',
        'WorkerDay_duplicate',
        'WorkerDay_delete_worker_days',
        'WorkerDay_exchange',
        'WorkerDay_confirm_vacancy',
        'WorkerDay_upload',
        'WorkerDay_upload_fact',
        'WorkerDay_download_timetable',
        'WorkerDay_download_tabel',
        'WorkerDay_editable_vacancy',
        'WorkerDay_approve_vacancy',
        'WorkerDay_change_range',
        'WorkerDay_request_approve',
        'WorkerPosition',
        'WorkTypeName',
        'WorkType',
        'WorkType_efficiency',
        'ShopMonthStat',
        'ShopMonthStat_status',
        'ShopSettings',
        'ShopSchedule',
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


def default_work_hours_by_months():
    return {f'm{month_num}': 100 for month_num in range(1, 12 + 1)}


class SAWHSettings(AbstractActiveNetworkSpecificCodeNamedModel):
    """
    Настройки суммированного учета рабочего времени.
    Модель нужна для распределения часов по месяцам в рамках учетного периода при автосоставлении.
    """
    year = models.PositiveSmallIntegerField(verbose_name='Год учетного периода')
    work_hours_by_months = JSONField(
        default=default_work_hours_by_months,
        verbose_name='Распределение рабочих часов по месяцам (в процентах)',
        help_text='Сумма часов в рамках учетного периода должна быть равна сумме часов по произв. календарю.',
    )  # Название ключей должно начинаться с m (например январь -- m1), чтобы можно было фильтровать через django orm
    positions = models.ManyToManyField('base.WorkerPosition', blank=True, verbose_name='Позиции')
    shops = models.ManyToManyField('base.Shop', blank=True, verbose_name='Подразделения')

    class Meta:
        verbose_name = 'Настройки суммированного учета рабочего времени'
        verbose_name_plural = 'Настройки суммированного учета рабочего времени'
        unique_together = (
            ('code', 'year', 'network'),
        )

    def __str__(self):
        return f'{self.name} {self.network.name}'

    def clean(self):
        if self.year and self.network.accounting_periods_count:
            current_year = datetime.datetime.now().year
            if self.year < current_year:
                raise ValidationError('Нельзя создавать/менять настройки за прошедшие года')

            for period_num_within_year in range(1, self.network.accounting_periods_count + 1):
                end_month = period_num_within_year * self.network.accounting_period_length
                start_month = end_month - (self.network.accounting_period_length - 1)

                summarized_account_period_work_hours_sum = sum(
                    v for k, v in self.work_hours_by_months.items() if start_month <= int(k.lstrip('m')) <= end_month)
                account_period_percents_summ = self.network.accounting_period_length * 100
                if summarized_account_period_work_hours_sum != account_period_percents_summ:
                    raise ValidationError(
                        f'В учетном периоде №{period_num_within_year} (месяца {start_month}-{end_month}) '
                        f'не сходится сумма процентов. '
                        f'Сeйчас {summarized_account_period_work_hours_sum}, должно быть {account_period_percents_summ}'
                    )


class ShopSchedule(AbstractModel):
    WORKDAY_TYPE = 'W'
    HOLIDAY_TYPE = 'H'

    SHOP_SCHEDULE_TYPES = (
        (WORKDAY_TYPE, 'Рабочий день'),
        (HOLIDAY_TYPE, 'Выходной'),
    )

    modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True, editable=False,
        verbose_name='Кем внесено расписание', help_text='Если null, то это стандартное расписание',
    )
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, verbose_name='Магазин')
    dt = models.DateField(verbose_name='Дата')
    opens = models.TimeField(verbose_name='Время открытия', null=True, blank=True)
    closes = models.TimeField(verbose_name='Время закрытия', null=True, blank=True)
    type = models.CharField(max_length=2, verbose_name='Тип', choices=SHOP_SCHEDULE_TYPES, default=WORKDAY_TYPE)

    tracker = FieldTracker(fields=['opens', 'closes', 'type'])

    class Meta:
        verbose_name = 'Расписание подразделения'
        verbose_name_plural = 'Расписание подразделения'
        unique_together = (
            ('dt', 'shop'),
        )
        ordering = ['dt']

    def __str__(self):
        return f'{self.shop.name} {self.dt} {self.opens}-{self.closes}'

    def clean(self):
        if self.type == self.WORKDAY_TYPE and self.opens is None or self.closes is None:
            raise ValidationError('opens and closes fields are required for workday type')

        if self.type == self.HOLIDAY_TYPE:
            self.opens = None
            self.closes = None

    def save(self, *args, **kwargs):
        recalc_wdays = kwargs.pop('recalc_wdays', False)

        if recalc_wdays and any(self.tracker.has_changed(f) for f in ['opens', 'closes', 'type']):
            from src.celery.tasks import recalc_wdays
            from src.util.models_converter import Converter
            dt_str = Converter.convert_date(self.dt)
            recalc_wdays.delay(
                shop_id=self.shop_id,
                dt_from=dt_str,
                dt_to=dt_str,
            )
        return super(ShopSchedule, self).save(*args, **kwargs)
