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
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db import transaction
from django.db.models import Case, When, Sum, Value, IntegerField, Subquery, OuterRef, F, Q
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker
from mptt.models import MPTTModel, TreeForeignKey
from rest_framework.serializers import ValidationError
from timezone_field import TimeZoneField

from src.base.models_abstract import (
    AbstractActiveModel,
    AbstractModel,
    AbstractActiveNetworkSpecificCodeNamedModel,
    NetworkSpecificModel,
    AbstractCodeNamedModel,
)
from src.conf.djconfig import QOS_TIME_FORMAT


class Network(AbstractActiveModel):
    ACC_PERIOD_MONTH = 1
    ACC_PERIOD_QUARTER = 3
    ACC_PERIOD_HALF_YEAR = 6
    ACC_PERIOD_YEAR = 12

    ACCOUNTING_PERIOD_LENGTH_CHOICES = (
        (ACC_PERIOD_MONTH, _('Month')),
        (ACC_PERIOD_QUARTER, _('Quarter')),
        (ACC_PERIOD_HALF_YEAR, _('Half a year')),
        (ACC_PERIOD_YEAR, _('Year')),
    )

    TABEL_FORMAT_CHOICES = (
        ('mts', 'MTSTabelGenerator'),
        ('t13_custom', 'CustomT13TabelGenerator'),
        ('aigul', 'AigulTabelGenerator'),
    )

    TIMETABLE_FORMAT_CHOICES = (
        ('cell_format', _('Cells')),
        ('row_format', _('Rows')),
    )

    CONVERT_TABEL_TO_CHOICES = (
        ('xlsx', 'xlsx'),
        ('pdf', 'PDF'),
    )

    class Meta:
        verbose_name = 'Сеть магазинов'
        verbose_name_plural = 'Сети магазинов'

    logo = models.ImageField(null=True, blank=True, upload_to='logo/%Y/%m', verbose_name=_('Logo'))
    url = models.CharField(blank=True, null=True, max_length=255)
    primary_color = models.CharField(max_length=7, blank=True, verbose_name=_('Primary color'))
    secondary_color = models.CharField(max_length=7, blank=True, verbose_name=_('Secondary color'))
    name = models.CharField(max_length=128, unique=True, verbose_name=_('Name'))
    code = models.CharField(max_length=64, unique=True, null=True, blank=True, verbose_name=_('Code'))
    # нужен ли идентификатор сотруднка чтобы откликнуться на вакансию
    need_symbol_for_vacancy = models.BooleanField(default=False, verbose_name=_('Need symbol for vacancy'))
    settings_values = models.TextField(default='{}', verbose_name=_('Settings values'))  # настройки для сети. Cейчас есть настройки для приемки чеков + ночные смены
    allowed_interval_for_late_arrival = models.DurationField(
        verbose_name=_('Allowed interval for late_arrival'), default=datetime.timedelta(seconds=0))
    allowed_interval_for_early_departure = models.DurationField(
        verbose_name=_('Allowed interval for early departure'), default=datetime.timedelta(seconds=0))
    allow_workers_confirm_outsource_vacancy = models.BooleanField(
        verbose_name=_('Allow workers confirm outsource vacancy'), default=False)
    okpo = models.CharField(blank=True, null=True, max_length=15, verbose_name=_('OKPO code'))
    allowed_geo_distance_km = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name=_('Allowed geo distance (km)'),
    )
    enable_camera_ticks = models.BooleanField(
        default=False, verbose_name=_('Enable camera ticks'))
    show_worker_day_additional_info = models.BooleanField(
        default=False, verbose_name=_('Show worker day additional info'),
        help_text=_('Displaying information about who last edited a worker day and when, when hovering over the corner'))
    show_worker_day_tasks = models.BooleanField(
        default=False, verbose_name=_('Show worker day tasks'))
    crop_work_hours_by_shop_schedule = models.BooleanField(
        default=False, verbose_name=_('Crop work hours by shop schedule')
    )
    clean_wdays_on_employment_dt_change = models.BooleanField(
        default=False, verbose_name=_('Clean worker days on employment date change'),
    )
    accounting_period_length = models.PositiveSmallIntegerField(
        choices=ACCOUNTING_PERIOD_LENGTH_CHOICES, verbose_name=_('Accounting period length'), default=1)
    only_fact_hours_that_in_approved_plan = models.BooleanField(
        default=False,
        verbose_name=_('Count only fact hours that in approved plan'),
    )
    copy_plan_to_fact_crossing = models.BooleanField(
        verbose_name=_("Copy plan to fact crossing"), default=False)
    download_tabel_template = models.CharField(
        max_length=64, verbose_name=_('Download tabel template'),
        choices=TABEL_FORMAT_CHOICES, default='mts',
    )
    timetable_format = models.CharField(
        max_length=64, verbose_name=_('Timetable format'),
        choices=TIMETABLE_FORMAT_CHOICES, default='cell_format',
    )
    convert_tabel_to = models.CharField(
        max_length=64, verbose_name=_('Convert tabel to'),
        null=True, blank=True,
        choices=CONVERT_TABEL_TO_CHOICES,
        default='xlsx',
    )
    breaks = models.ForeignKey(
        'base.Break',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_('Default breaks'),
        related_name='networks',
    )
    load_template = models.ForeignKey(
        'forecast.LoadTemplate',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_('Default load template'),
        related_name='networks',
    )
    # при создании новой должности будут проставляться соотв. значения
    # пример значения можно найти в src.base.tests.test_worker_position.TestSetWorkerPositionDefaultsModel
    worker_position_default_values = models.TextField(verbose_name=_('Worker position default values'), default='{}')
    descrease_employment_dt_fired_in_api = models.BooleanField(
        default=False, verbose_name=_('Descrease employment date fired in api'),
        help_text=_('Relevant for data received via the api'),
    )
    consider_remaining_hours_in_prev_months_when_calc_norm_hours = models.BooleanField(
        default=False, verbose_name=_('Consider remaining hours in previous months when calculating norm hours'),
    )
    outsourcings = models.ManyToManyField(
        'self', through='base.NetworkConnect', through_fields=('client', 'outsourcing'), symmetrical=False, related_name='clients')
    ignore_parent_code_when_updating_department_via_api = models.BooleanField(
        default=False, verbose_name=_('Ignore parent code when updating department via api'),
        help_text=_('It must be enabled for cases when the organizational structure is maintained manually'),
    )
    create_employment_on_set_or_update_director_code = models.BooleanField(
        default=False,
        verbose_name=_('Create employment on set or update director code'),
    )
    show_user_biometrics_block = models.BooleanField(
        default=False,
        verbose_name=_('Show user biometrics block'),
    )

    @property
    def settings_values_prop(self):
        return json.loads(self.settings_values)

    def set_settings_value(self, k, v):
        settings_values = json.loads(self.settings_values)
        settings_values[k] = v
        self.settings_values = json.dumps(settings_values)

    def get_department(self):
        return None

    @cached_property
    def position_default_values(self):
        return json.loads(self.worker_position_default_values)

    @cached_property
    def night_edges(self):
        default_night_edges = (
            '22:00:00',
            '06:00:00',
        )
        return self.settings_values_prop.get('night_edges', default_night_edges)

    @cached_property
    def night_edges_tm_list(self):
        from src.util.models_converter import Converter
        return [Converter.parse_time(t) for t in self.night_edges]

    @cached_property
    def accounting_periods_count(self):
        return int(12 / self.accounting_period_length)

    def get_acc_period_range(self, dt=None, year=None, period_num=None):
        assert dt or (year and period_num)
        if dt:
            period_num_within_year = dt.month // self.accounting_period_length
            if dt.month % self.accounting_period_length > 0:
                period_num_within_year += 1
            year = dt.year
        if period_num:
            period_num_within_year = period_num
        end_month = period_num_within_year * self.accounting_period_length
        start_month = end_month - (self.accounting_period_length - 1)

        return datetime.date(year, start_month, 1), \
            datetime.date(year, end_month, monthrange(year, end_month)[1])

    def __str__(self):
        return f'name: {self.name}, code: {self.code}'


class NetworkConnect(AbstractActiveModel):
    class Meta:
        verbose_name = 'Связь сетей'
        verbose_name_plural = 'Связи сетей'

    client = models.ForeignKey(Network, related_name='outsourcing_connections', on_delete=models.PROTECT)
    outsourcing = models.ForeignKey(Network, related_name='outsourcing_clients', on_delete=models.PROTECT)


class Region(AbstractActiveNetworkSpecificCodeNamedModel):
    parent = models.ForeignKey(
        to='self', verbose_name='Родительский регион', on_delete=models.CASCADE,
        null=True, blank=True, related_name='children',
    )

    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'


class Break(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Перерыв'
        verbose_name_plural = 'Перерывы'
    value = models.CharField(max_length=1024, default='[]')

    @property
    def breaks(self):
        return json.loads(self.value)

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
        breaks = self.breaks
        for b in breaks:
            if not isinstance(b, list) or len(b) != 3 or ((not isinstance(b[0], int)) or (not isinstance(b[1], int)) or (not isinstance(b[2], list))):
                raise ValidationError(_('Bad break triplet format {triplet}, should be [[int, int, [int, int,]],].').format(triplet=b))

            if b[0] > b[1]:
                raise ValidationError(_('First value of period can not be greater then second value: {triplet}').format(triplet=b))
            
            if not all([isinstance(v, int) for v in b[2]]):
                raise ValidationError(_('Bad break triplet format {triplet}, should be [[int, int, [int, int,]],].').format(triplet=b))
            
            if any([v > b[1] for v in b[2]]):
                raise ValidationError(_('Value of break can not be greater than value of period: {triplet}').format(triplet=b))

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
    norm_hours_coeff = models.FloatField(default=1.0, verbose_name='Коэфф. нормы часов')
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
    fias_code = models.CharField(max_length=300, blank=True)
    type = models.CharField(max_length=1, choices=DEPARTMENT_TYPES, default=TYPE_SHOP)

    dt_opened = models.DateField(null=True, blank=True)
    dt_closed = models.DateField(null=True, blank=True)

    mean_queue_length = models.FloatField(default=3)
    max_queue_length = models.FloatField(default=7)
    dead_time_part = models.FloatField(default=0.1)

    beta = models.FloatField(default=0.9)  # for creating timetable, (a function from previous 3 variables)

    demand_coef = models.FloatField(default=1)  # unknown trend for algorithm

    forecast_step_minutes = models.TimeField(default=datetime.time(hour=1))
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

    latitude = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True, verbose_name='Широта')
    longitude = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True, verbose_name='Долгота')
    director = models.ForeignKey('base.User', null=True, blank=True, verbose_name='Директор', on_delete=models.SET_NULL)
    city = models.CharField(max_length=128, null=True, blank=True, verbose_name='Город')

    tracker = FieldTracker(
        fields=['tm_open_dict', 'tm_close_dict', 'load_template', 'latitude', 'longitude', 'fias_code', 'director_id'])

    def __str__(self):
        return '{}, {}, {}, {}'.format(
            self.name,
            self.parent_title(),
            self.id,
            self.code,
        )

    @property
    def is_active(self):
        dttm_now = timezone.now()
        dt_now = dttm_now.date()
        is_not_deleted = self.dttm_deleted is None or (self.dttm_added < dttm_now < self.dttm_deleted)
        is_not_closed = (self.dt_opened or datetime.date(1000, 1, 1)) <= dt_now <= (
                    self.dt_closed or datetime.date(3999, 1, 1))
        return is_not_deleted and is_not_closed

    @is_active.setter
    def is_active(self, val):
        # TODO: нужно ли тут проставлять dt_closed?
        if val:
            if self.dttm_deleted:
                self.dttm_deleted = None
        else:
            if not self.dttm_deleted:
                self.dttm_deleted = timezone.now()

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

    def _get_parent_or_400(self, parent_code):
        try:
            return Shop.objects.get(code=parent_code)
        except Shop.DoesNotExist:
            raise ValidationError(_('Shop with parent_code={code} not found').format(code=parent_code))

    def __init__(self, *args, **kwargs):
        parent_code = kwargs.pop('parent_code', None)
        super().__init__(*args, **kwargs)
        if parent_code:
            self.parent = self._get_parent_or_400(parent_code)

    @property
    def director_code(self):
        return getattr(self.director, 'username', None)

    @director_code.setter
    def director_code(self, val):
        if val:
            director = User.objects.filter(username=val).first()
            if director:
                self.director = director

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

    def _fill_city_from_coords(self):
        if not self.city and self.latitude and self.longitude and settings.DADATA_TOKEN:
            from src.base.shop.tasks import fill_shop_city_from_coords
            fill_shop_city_from_coords.delay(shop_id=self.id)

    def _fill_city_coords_address_timezone_from_fias_code(self):
        if self.fias_code and settings.DADATA_TOKEN:
            from src.base.shop.tasks import fill_city_coords_address_timezone_from_fias_code
            fill_city_coords_address_timezone_from_fias_code.delay(shop_id=self.id)

    def _handle_new_shop_created(self):
        from src.util.models_converter import Converter
        from src.base.shop.tasks import fill_shop_schedule
        dt_now = datetime.datetime.now().date()
        if self.open_times and self.close_times:
            fill_shop_schedule.delay(
                shop_id=self.id,
                dt_from=Converter.convert_date(dt_now - datetime.timedelta(days=30)),
                periods=120,
            )

    def _handle_schedule_change(self):
        from src.util.models_converter import Converter
        from src.base.shop.tasks import fill_shop_schedule
        from src.timetable.worker_day.tasks import recalc_wdays
        dt_now = datetime.datetime.now().date()
        ch = chain(
            fill_shop_schedule.si(shop_id=self.id, dt_from=Converter.convert_date(dt_now)),
            recalc_wdays.si(
                shop_id=self.id,
                dt__gte=Converter.convert_date(dt_now),
                dt__lte=Converter.convert_date(dt_now + datetime.timedelta(days=90))),
        )
        ch.apply_async()

    def _create_director_employment(self):
        employee, _employee_created = Employee.objects.get_or_create(
            user_id=self.director_id,
            tabel_code=None,
        )
        shop_lvl_to_role_code_mapping = self.network.settings_values_prop.get(
            'shop_lvl_to_role_code_mapping', {})
        role_code = shop_lvl_to_role_code_mapping.get(str(self.get_level()))
        if role_code:
            role = Group.objects.filter(code=role_code, network_id=self.network_id).first()
            if role:
                Employment.objects.update_or_create(
                    employee=employee,
                    shop=self,
                    is_visible=False,
                    defaults=dict(
                        function_group=role,
                        dt_hired=timezone.now().date(),
                        dt_fired='3999-01-01',
                    )
                )

    def save(self, *args, force_create_director_employment=False, **kwargs):
        is_new = self.id is None
        if self.open_times.keys() != self.close_times.keys():
            raise ValidationError(_('Keys of open times and close times are different.'))
        if self.open_times.get('all') and len(self.open_times) != 1:
            raise ValidationError(_('\'All\' and individual days cannot be specified.'))
        
        #TODO fix
        # for key in open_times.keys():
        #     close_hour = close_times[key].hour if close_times[key].hour != 0 else 24
        #     if open_times[key].hour > close_hour:
        #         raise MessageError(code='time_shop_incorrect_time_start_end')
        self.tm_open_dict = self.clean_time_dict(self.open_times)
        self.tm_close_dict = self.clean_time_dict(self.close_times)
        if hasattr(self, 'parent_code'):
            self.parent = self._get_parent_or_400(self.parent_code)
        load_template_changed = self.tracker.has_changed('load_template')
        if load_template_changed and self.load_template_status == self.LOAD_TEMPLATE_PROCESS:
            raise ValidationError(_('It is not possible to change the load template as it is in the calculation process.'))
        res = super().save(*args, **kwargs)
        if is_new:
            transaction.on_commit(self._handle_new_shop_created)
        elif self.tracker.has_changed('tm_open_dict') or self.tracker.has_changed('tm_close_dict'):
            transaction.on_commit(self._handle_schedule_change)
        
        if is_new and self.load_template_id is None:
            self.load_template_id = self.network.load_template_id

        if load_template_changed and not (self.load_template_id is None):
            from src.forecast.load_template.utils import apply_load_template
            from src.forecast.load_template.tasks import calculate_shops_load
            apply_load_template(self.load_template_id, self.id)
            calculate_shops_load.delay(
                self.load_template_id,
                datetime.date.today(),
                datetime.date.today().replace(day=1) + relativedelta(months=1),
                shop_id=self.id,
            )

        if is_new or (self.tracker.has_changed('latitude') or self.tracker.has_changed('longitude')) and \
                settings.FILL_SHOP_CITY_FROM_COORDS:
            transaction.on_commit(self._fill_city_from_coords)

        if is_new or self.tracker.has_changed('fias_code') and settings.FILL_SHOP_CITY_COORDS_ADDRESS_TIMEZONE_FROM_FIAS_CODE:
            transaction.on_commit(self._fill_city_coords_address_timezone_from_fias_code)

        if self.network.create_employment_on_set_or_update_director_code or force_create_director_employment:
            if is_new:
                if self.director_id:
                    self._create_director_employment()
            else:
                if self.tracker.has_changed('director_id') or force_create_director_employment:
                    if self.director_id:
                        self._create_director_employment()

                    prev_director_id_value = self.tracker.previous('director_id')
                    if self.tracker.has_changed('director_id') and prev_director_id_value:
                        empls_to_delete_qs = Employment.objects.filter(
                            employee__user_id=prev_director_id_value,
                            employee__tabel_code__isnull=True,
                            shop=self,
                            is_visible=False,
                            dt_fired='3999-01-01',
                        )
                        empls_to_delete_qs.update(dt_fired=timezone.now().date())
                        empls_to_delete_qs.delete()

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

    @cached_property
    def is_all_day(self):
        if self.open_times and self.close_times:
            open_at_0 = all(getattr(d, a) == 0 for a in ['hour', 'second', 'minute'] for d in self.open_times.values())
            close_at_0 = all(getattr(d, a) == 0 for a in ['hour', 'second', 'minute'] for d in self.close_times.values())
            shop_24h_open = open_at_0 and close_at_0
            return shop_24h_open


class EmploymentManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(dttm_deleted__date__gt=timezone.now().date()) | models.Q(dttm_deleted__isnull=True)
        )

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
                employee__user__network_id=network_id,
            )
        qs = self.filter(q)
        return qs.filter(*args, **kwargs)

    def get_active_empl_by_priority(
            self, network_id, dt=None, priority_shop_id=None, priority_employment_id=None,
            priority_work_type_id=None, priority_by_visible=True, **kwargs):
        qs = self.get_active(network_id, dt_from=dt, dt_to=dt, **kwargs)

        order_by = []

        if priority_by_visible:
            order_by.append('-is_visible')

        if priority_employment_id:
            qs = qs.annotate_value_equality(
                'is_equal_employments', 'id', priority_employment_id,
            )
            order_by.append('-is_equal_employments')

        if priority_shop_id:
            qs = qs.annotate_value_equality(
                'is_equal_shops', 'shop_id', priority_shop_id,
            )
            order_by.append('-is_equal_shops')

        if priority_work_type_id:
            qs = qs.annotate_value_equality(
                'is_equal_work_types', 'work_types__work_type_id', priority_work_type_id,
            ).distinct()
            order_by.append('-is_equal_work_types')

        order_by.append('-norm_work_hours')

        return qs.order_by(*order_by)



class Group(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Группа пользователей'
        verbose_name_plural = 'Группы пользователей'

    dttm_modified = models.DateTimeField(blank=True, null=True)
    subordinates = models.ManyToManyField("self", blank=True)
    has_perm_to_change_protected_wdays = models.BooleanField(
        default=False, verbose_name='Может изменять/подтверждать "защищенные" рабочие дни')

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
        q = Q(
            Q(region_id=region_id) | Q(region__parent_id=region_id),
            dt__year=year,
            type__in=ProductionDay.WORK_TYPES,
        )
        if month:
            q &= Q(dt__month=month)

        prod_cal_subq = ProductionDay.objects.filter(q).annotate(
            is_equal_regions=Case(
                When(region_id=Value(region_id), then=True),
                default=False, output_field=models.BooleanField()
            ),
        ).order_by('-is_equal_regions')

        norm_work_hours = ProductionDay.objects.filter(
            q,
            id=Subquery(prod_cal_subq.values_list('id', flat=True)[:1])
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

    LOCAL_AUTH = 'local'
    LDAP_AUTH = 'ldap'
    AUTH_TYPES = (
        (LOCAL_AUTH, 'Локально'),
        (LDAP_AUTH, 'LDAP'),
    )
    sex = models.CharField(
        max_length=1,
        default=SEX_FEMALE,
        choices=SEX_CHOICES,
    )
    avatar = models.ImageField(null=True, blank=True, upload_to='user_avatar/%Y/%m')
    phone_number = models.CharField(max_length=32, null=True, blank=True)
    access_token = models.CharField(max_length=64, blank=True, null=True)
    code = models.CharField(blank=True, max_length=64, null=True, unique=True)
    lang = models.CharField(max_length=2, default='ru')
    network = models.ForeignKey(Network, on_delete=models.PROTECT, null=True)
    black_list_symbol = models.CharField(max_length=128, null=True, blank=True)
    auth_type = models.CharField(
        max_length=10,
        default=LOCAL_AUTH,
        choices=AUTH_TYPES,
    )

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

    def get_active_employments(self, shop=None):
        kwargs = {
            'employee__user__network_id': self.network_id,
            'shop__network_id': self.network_id,
        }
        if shop:
            kwargs['shop__in'] = shop.get_ancestors(include_self=True)
        return Employment.objects.filter(
            employee__user=self,
            **kwargs,
        )

    def get_group_ids(self, shop=None):
        return self.get_active_employments(shop=shop).annotate(
            group_id=Coalesce(F('function_group_id'), F('position__group_id')),
        ).values_list('group_id', flat=True)

    def save(self, *args, **kwargs):
        if not self.password and settings.SET_USER_PASSWORD_AS_LOGIN:
            self.set_password(self.username)

        return super(User, self).save(*args, **kwargs)


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
    ordering = models.PositiveSmallIntegerField(default=9999, verbose_name='Индекс должности для сортировки')

    def __str__(self):
        return '{}, {}'.format(self.name, self.id)

    @cached_property
    def wp_defaults(self):
        wp_defaults_dict = self.network.position_default_values
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

    def save(self, *args, force_set_defaults=False, **kwargs):
        is_new = self.id is None
        if is_new or force_set_defaults:
            self._set_plain_defaults()
        res = super(WorkerPosition, self).save(*args, **kwargs)
        if is_new or force_set_defaults:
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

    def delete(self):
        from src.timetable.models import WorkerDay
        from src.timetable.worker_day.tasks import clean_wdays
        with transaction.atomic():
            wdays_ids = list(WorkerDay.objects.filter(employment__in=self).values_list('id', flat=True))
            WorkerDay.objects.filter(employment__in=self).update(employment_id=None)
            self.update(dttm_deleted=timezone.now())
            transaction.on_commit(lambda: clean_wdays.delay(
                only_logging=False,
                filter_kwargs=dict(
                    id__in=wdays_ids,
                ),
            ))


class Employee(AbstractModel):
    code = models.CharField(max_length=128, null=True, blank=True, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="employees")
    tabel_code = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        unique_together = (
            ('tabel_code', 'user'),
        )

    def __str__(self):
        s = self.user.fio
        if self.tabel_code:
            s += f' ({self.tabel_code})'
        return s


class Employment(AbstractActiveModel):
    class Meta:
        verbose_name = 'Трудоустройство'
        verbose_name_plural = 'Трудоустройства'

    def __str__(self):
        return '{}, {}, {}'.format(self.id, self.shop, self.employee)

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=128, null=True, blank=True, unique=True)
    employee = models.ForeignKey(
        'base.Employee', on_delete=models.CASCADE, related_name="employments")
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
    norm_work_hours = models.FloatField(default=100)
    shift_hours_length_min = models.SmallIntegerField(blank=True, null=True)
    shift_hours_length_max = models.SmallIntegerField(blank=True, null=True)
    min_time_btw_shifts = models.SmallIntegerField(blank=True, null=True)

    auto_timetable = models.BooleanField(default=True)

    is_ready_for_overworkings = models.BooleanField(default=False)

    dt_new_week_availability_from = models.DateField(null=True, blank=True)
    is_visible = models.BooleanField(default=True)

    tracker = FieldTracker(fields=['position', 'dt_hired', 'dt_fired'])

    objects = EmploymentManager.from_queryset(EmploymentQuerySet)()
    objects_with_excluded = models.Manager.from_queryset(EmploymentQuerySet)()

    def has_permission(self, permission, method='GET'):
        group = self.function_group or (self.position.group if self.position else None)
        if not group:
            raise ValidationError(_('Unable to define worker access group. Assign an access group to him or a position associated with an access group.'))
        return group.allowed_functions.filter(
            func=permission,
            method=method
        ).first()

    def get_department(self):
        return self.shop

    def get_short_fio_and_position(self):
        short_fio_and_position = f'{self.employee.user.get_short_fio()}'
        if self.position and self.position.name:
            short_fio_and_position += f', {self.position.name}'

        return short_fio_and_position

    def delete(self, **kwargs):
        from src.timetable.models import WorkerDay
        from src.timetable.worker_day.tasks import clean_wdays
        with transaction.atomic():
            wdays_ids = list(WorkerDay.objects.filter(employment=self).values_list('id', flat=True))
            WorkerDay.objects.filter(employment=self).update(employment_id=None)
            if self.employee.user.network.clean_wdays_on_employment_dt_change:
                transaction.on_commit(lambda: clean_wdays.delay(
                    only_logging=False,
                    filter_kwargs=dict(
                        id__in=wdays_ids,
                    ),
                ))
            return super(Employment, self).delete(**kwargs)

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
            self.employee, _employee_created = Employee.objects.get_or_create(
                user=User.objects.get(username=self.username), tabel_code=self.tabel_code)
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
                self.employee.user.network and self.employee.user.network.clean_wdays_on_employment_dt_change:
            from src.timetable.worker_day.tasks import clean_wdays
            from src.timetable.models import WorkerDay
            from src.util.models_converter import Converter
            kwargs = {
                'only_logging': False,
                'clean_plan_empl': True,
            }
            if is_new:
                kwargs['filter_kwargs'] = {
                    'type': WorkerDay.TYPE_WORKDAY,
                    'employee_id': self.employee_id,
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
                    'employee_id': self.employee_id,
                    'dt__gte': Converter.convert_date(dt__gte),
                }

            clean_wdays.apply_async(kwargs=kwargs)

        return res

    def is_active(self, dt=None):
        dt = dt or timezone.now().date()
        return (self.dt_hired is None or self.dt_hired <= dt) and (self.dt_fired is None or self.dt_fired >= dt)


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

    FUNCS_TUPLE = (
        ('AutoSettings_create_timetable', 'Составление графика (Создать)'),
        ('AutoSettings_set_timetable', 'Задать график (ответ от алгоритмов, Создать)'),
        ('AutoSettings_delete_timetable', 'Удалить график (Создать)'),
        ('AuthUserView', 'Получить авторизованного пользователя'),
        ('Break', 'Перерыв'),
        ('Employment', 'Трудоустройство'),
        ('Employee', 'Сотрудник'),
        ('Employment_auto_timetable', 'Выбрать сорудников для автосоставления (Создать)'),
        ('Employment_timetable', 'Редактирование полей трудоустройства, связанных с расписанием'),
        ('EmploymentWorkType', 'Связь трудоустройства и типа работ'),
        ('ExchangeSettings', 'Настройки обмена сменами'),
        ('FunctionGroupView', 'Доступ к функциям'),
        ('FunctionGroupView_functions', 'Получить список доступных функций (Получить)'),
        ('LoadTemplate', 'Шаблон нагрузки'),
        ('LoadTemplate_apply', 'Применить шаблон нагрузки (Создать)'),
        ('LoadTemplate_calculate', 'Рассчитать нагрузку (Создать)'),
        ('LoadTemplate_download', 'Скачать шаблон нагрузки (Получить)'),
        ('LoadTemplate_upload', 'Загрузить шаблон нагрузки (Создать)'),
        ('Network', 'Сеть'),
        ('Notification', 'Уведомление'),
        ('OperationTemplate', 'Шаблон операции'),
        ('OperationTypeName', 'Название типа операции'),
        ('OperationType', 'Тип операции'),
        ('OperationTypeRelation', 'Отношение типов операций'),
        ('OperationTypeTemplate', 'Шаблон типа операции'),
        ('PeriodClients', 'Нагрузка'),
        ('PeriodClients_indicators', 'Индикаторы нагрузки (Получить)'),
        ('PeriodClients_put', 'Обновить нагрузку (Обновить)'),
        ('PeriodClients_delete', 'Удалить нагрузку (Удалить)'),
        ('PeriodClients_upload', 'Загрузить нагрузку (Создать)'),
        ('PeriodClients_download', 'Скачать нагрузку (Получить)'),
        ('Receipt', 'Чек'),
        ('Group', 'Группа доступа'),
        ('Shop', 'Отдел'),
        ('Shop_stat', 'Статистика по отделам (Получить)'),
        ('Shop_tree', 'Дерево отделов (Получить)'),
        ('Shop_outsource_tree', 'Дерево отделов клиентов (для аутсорс компаний) (Получить)'),
        ('Subscribe', 'Subscribe'),
        ('TickPoint', 'Точка отметки'),
        ('Timesheet', 'Табель'),
        ('Timesheet_stats', 'Статистика табеля (Получить)'),
        ('Timesheet_recalc', 'Запустить пересчет табеля (Создать)'),
        ('User', 'Пользователь'),
        ('User_change_password', 'Сменить пароль пользователю (Создать)'),
        ('User_delete_biometrics', 'Удалить биометрию пользователя (Создать)'),
        ('User_add_biometrics', 'Добавить биометрию пользователя (Создать)'),
        ('WorkerConstraint', 'Ограничения сотрудника'),
        ('WorkerDay', 'Рабочий день'),
        ('WorkerDay_approve', 'Подтвердить график (Создать)'),
        ('WorkerDay_daily_stat', 'Статистика по дням (Получить)'),
        ('WorkerDay_worker_stat', 'Статистика по работникам (Получить)'),
        ('WorkerDay_vacancy', 'Список вакансий (Получить)'),
        ('WorkerDay_change_list', 'Редактирование дней списоком (Создать)'),
        ('WorkerDay_copy_approved', 'Копировать рабочие дни из разных версий (Создать)'),
        ('WorkerDay_copy_range', 'Копировать дни на следующий месяц (Создать)'),
        ('WorkerDay_duplicate', 'Копировать рабочие дни как ячейки эксель (Создать)'),
        ('WorkerDay_delete_worker_days', 'Удалить рабочие дни (Создать)'),
        ('WorkerDay_exchange', 'Обмен сменами (Создать)'),
        ('WorkerDay_exchange_approved', 'Обмен подтвержденными сменами (Создать)'),
        ('WorkerDay_confirm_vacancy', 'Откликнуться вакансию (Создать)'),
        ('WorkerDay_confirm_vacancy_to_worker', 'Назначить работника на вакансию (Создать)'),
        ('WorkerDay_reconfirm_vacancy_to_worker', 'Переназначить работника на вакансию (Создать)'),
        ('WorkerDay_upload', 'Загрузить плановый график (Создать)'),
        ('WorkerDay_upload_fact', 'Загрузить фактический график (Создать)'),
        ('WorkerDay_download_timetable', 'Скачать плановый график (Получить)'),
        ('WorkerDay_download_tabel', 'Скачать табель (Получить)'),
        ('WorkerDay_editable_vacancy', 'Получить редактируемую вакансию (Получить)'),
        ('WorkerDay_approve_vacancy', 'Подтвердить вакансию (Создать)'),
        ('WorkerDay_change_range', 'Создание/обновление дней за период (Создать)'),
        ('WorkerDay_request_approve', 'Запросить подтверждение графика (Создать)'),
        ('WorkerDay_block', 'Заблокировать рабочий день (Создать)'),
        ('WorkerDay_unblock', 'Разблокировать рабочий день (Создать)'),
        ('WorkerDay_generate_upload_example', 'Скачать шаблон графика (Получить)'),
        ('WorkerDay_recalc', 'Пересчитать часы (Создать)'),
        ('WorkerPosition', 'Должность'),
        ('WorkTypeName', 'Название типа работ'),
        ('WorkType', 'Тип работ'),
        ('WorkType_efficiency', 'Покрытие (Получить)'),
        ('ShopMonthStat', 'Статистика по магазину на месяц'),
        ('ShopMonthStat_status', 'Статус составления графика (Получить)'),
        ('ShopSettings', 'Настройки автосоставления'),
        ('ShopSchedule', 'Расписание магазина'),
        ('VacancyBlackList', 'Черный список для вакансий'),
        ('Task', 'Задача'),
    )

    METHODS_TUPLE = (
        ('GET', 'Получить'),
        ('POST', 'Создать'),
        ('PUT', 'Обновить'),
        ('DELETE', 'Удалить'),
    )

    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_modified = models.DateTimeField(blank=True, null=True)
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name='allowed_functions', blank=True, null=True)
    func = models.CharField(max_length=128, choices=FUNCS_TUPLE, help_text='В скобках указывается метод с которым работает данная функция')
    method = models.CharField(max_length=6, choices=METHODS_TUPLE, default='GET')
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


def current_year():
    return datetime.datetime.now().year


class SAWHSettings(AbstractActiveNetworkSpecificCodeNamedModel):
    """
    Настройки суммированного учета рабочего времени.
    Модель нужна для распределения часов по месяцам в рамках учетного периода.
    """

    PART_OF_PROD_CAL_SUMM = 1
    FIXED_HOURS = 2

    SAWH_SETTINGS_TYPES = (
        (PART_OF_PROD_CAL_SUMM, 'Доля от суммы часов по произв. календарю в рамках уч. периода'),
        (FIXED_HOURS, 'Фикс. кол-во часов в месяц'),
    )

    work_hours_by_months = JSONField(
        verbose_name='Настройки по распределению часов в рамках уч. периода',
    )  # Название ключей должно начинаться с m (например январь -- m1), чтобы можно было фильтровать через django orm
    type = models.PositiveSmallIntegerField(
        default=PART_OF_PROD_CAL_SUMM, choices=SAWH_SETTINGS_TYPES, verbose_name='Тип расчета')

    class Meta:
        verbose_name = 'Настройки суммированного учета рабочего времени'
        verbose_name_plural = 'Настройки суммированного учета рабочего времени'

    def __str__(self):
        return f'{self.name} {self.network.name}'


class SAWHSettingsMapping(AbstractModel):
    sawh_settings = models.ForeignKey('base.SAWHSettings', on_delete=models.CASCADE, verbose_name='Настройки СУРВ')
    year = models.PositiveSmallIntegerField(verbose_name='Год учетного периода', default=current_year)
    shops = models.ManyToManyField('base.Shop', blank=True)
    positions = models.ManyToManyField('base.WorkerPosition', blank=True, related_name='+')
    exclude_positions = models.ManyToManyField('base.WorkerPosition', blank=True, related_name='+')
    priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Настройки суммированного учета рабочего времени'
        verbose_name_plural = 'Настройки суммированного учета рабочего времени'


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
            from src.timetable.worker_day.tasks import recalc_wdays
            from src.util.models_converter import Converter
            dt_str = Converter.convert_date(self.dt)
            recalc_wdays.delay(
                shop_id=self.shop_id,
                dt__gte=dt_str,
                dt__lte=dt_str,
            )
        return super(ShopSchedule, self).save(*args, **kwargs)
