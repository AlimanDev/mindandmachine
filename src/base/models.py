import datetime
import json
import re
from calendar import monthrange
from decimal import Decimal

import pandas as pd
from celery import chain
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse
from django.conf import settings
from django.contrib.auth.models import (
    AbstractUser as DjangoAbstractUser,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.core.cache import cache
from django.db import models, router
from django.db import transaction
from django.db.models import Case, When, Sum, Value, IntegerField, Subquery, OuterRef, Q
from django.db.models.deletion import Collector
from django.db.models.query import QuerySet
from django.template import Template, Context
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker
from mptt.models import MPTTModel, TreeForeignKey, TreeManager
from rest_framework.exceptions import PermissionDenied
from rest_framework.serializers import ValidationError
from timezone_field import TimeZoneField

from src.base.fields import MultipleChoiceField
from src.base.models_abstract import (
    AbstractActiveModel,
    AbstractModel,
    AbstractActiveNetworkSpecificCodeNamedModel,
)
from src.base.models_utils import OverrideBaseManager, current_year
from src.conf.djconfig import QOS_TIME_FORMAT
from src.util.mixins.qs import AnnotateValueEqualityQSMixin
from src.util import images
from src.timetable.timesheet import min_threshold_funcs


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

    WD_FACT_APPROVED = 1
    FACT_TIMESHEET = 2
    MAIN_TIMESHEET = 3

    PREV_MONTHS_WORK_HOURS_SOURCE_CHOICES = (
        (WD_FACT_APPROVED, 'Факт. подтв. график'),
        (FACT_TIMESHEET, 'Фактический табель'),
        (MAIN_TIMESHEET, 'Основной табель'),
    )

    TIMESHEET_LINES_GROUP_BY_EMPLOYEE = 1
    TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION = 2
    TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION_SHOP = 3

    TIMESHEET_LINES_GROUP_BY_CHOICES = (
        (TIMESHEET_LINES_GROUP_BY_EMPLOYEE, 'Сотруднику'),
        (TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION, 'Сотруднику и должности'),
        (TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION_SHOP, 'Сотруднику, должности и подразделению выхода'),
    )

    FISCAL_SHEET_DIVIDERS_ALIAS_CHOICES = (
        ('nahodka', 'Находка'),
        ('pobeda', 'Победа'),
        ('pobeda_manual', 'Победа с ручным проставлением доп. смен'),
        ('shift_schedule', 'По расписанию смен'),
    )

    TABEL_FORMAT_CHOICES = (
        ('mts', 'MTSTimesheetGenerator'),
        ('t13_custom', 'CustomT13TimesheetGenerator'),
        ('default', 'DefaultTimesheetGenerator'),
        ('lines', 'TimesheetLinesGenerator'),
    )

    TIMETABLE_FORMAT_CHOICES = (
        ('cell_format', _('Cells')),
        ('row_format', _('Rows')),
    )

    CONVERT_TABEL_TO_CHOICES = (
        ('xlsx', 'xlsx'),
        ('pdf', 'PDF'),
    )

    ROUND_TO_HALF_AN_HOUR = 0
    ROUND_WH_ALGS = {
        ROUND_TO_HALF_AN_HOUR: lambda wh: round(wh * 2) / 2,
    }
    ROUND_WORK_HOURS_ALG_CHOICES = (
        (ROUND_TO_HALF_AN_HOUR, 'Округление до получаса'),
    )

    DEFAULT_NIGHT_EDGES = (
        '22:00:00',
        '06:00:00',
    )

    class Meta:
        verbose_name = 'Сеть магазинов'
        verbose_name_plural = 'Сети магазинов'

    name = models.CharField(max_length=128, unique=True, verbose_name=_('Name'))
    code = models.CharField(max_length=64, unique=True, null=True, blank=True, verbose_name=_('Code'))
    logo = models.ImageField(null=True, blank=True, upload_to='logo/%Y/%m', verbose_name=_('Logo'))
    url = models.CharField(blank=True, null=True, max_length=255)
    primary_color = models.CharField(max_length=7, blank=True, verbose_name=_('Primary color'))
    secondary_color = models.CharField(max_length=7, blank=True, verbose_name=_('Secondary color'))
    outsourcings = models.ManyToManyField(
        'self', through='base.NetworkConnect', through_fields=('client', 'outsourcing'), symmetrical=False, related_name='clients')
    settings_values = models.TextField(default='{}', verbose_name=_('Settings values')) # General network settings, stored as JSON (see settings_values_prop property) TODO: update to actual JSON field instead of Text


    # Network settings
    accounting_period_length = models.PositiveSmallIntegerField(
        choices=ACCOUNTING_PERIOD_LENGTH_CHOICES, verbose_name=_('Accounting period length'), default=1)
    add_users_from_excel = models.BooleanField(default=False, verbose_name=_('Upload employments from excel'),)
    allow_creation_several_wdays_for_one_employee_for_one_date = models.BooleanField(
        default=False, verbose_name='Разрешить создание нескольких рабочих дней для 1 сотрудника на 1 дату')
    allowed_geo_distance_km = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name=_('Allowed geo distance (km)'),
    )
    allowed_interval_for_early_arrival = models.DurationField(
        verbose_name=_('Allowed interval for early arrival'), default=datetime.timedelta(seconds=0))
    allowed_interval_for_early_departure = models.DurationField(
        verbose_name=_('Allowed interval for early departure'), default=datetime.timedelta(seconds=0))
    allowed_interval_for_late_arrival = models.DurationField(
        verbose_name=_('Allowed interval for late_arrival'), default=datetime.timedelta(seconds=0))
    allowed_interval_for_late_departure = models.DurationField(
        verbose_name=_('Allowed interval for late departure'), default=datetime.timedelta(minutes=15))
    allow_workers_confirm_outsource_vacancy = models.BooleanField(
        verbose_name=_('Allow workers confirm outsource vacancy'), default=False)
    api_timesheet_lines_group_by = models.PositiveSmallIntegerField(
        verbose_name='Группировать данные табеля в api методе /rest_api/timesheet/lines/ по',
        choices=TIMESHEET_LINES_GROUP_BY_CHOICES, default=TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION_SHOP)
    biometry_in_tick_report = models.BooleanField(default=False, verbose_name=_('Include biometry (photos) in tick report'))
    breaks = models.ForeignKey(
        'base.Break',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_('Default breaks'),
        related_name='networks',
    )
    consider_remaining_hours_in_prev_months_when_calc_norm_hours = models.BooleanField(
        default=False, verbose_name=_('Consider remaining hours in previous months when calculating norm hours'),
    )
    convert_tabel_to = models.CharField(
        max_length=64, verbose_name=_('Convert tabel to'),
        null=True, blank=True,
        choices=CONVERT_TABEL_TO_CHOICES,
        default='xlsx',
    )
    copy_plan_to_fact_crossing = models.BooleanField(
        verbose_name=_("Copy plan to fact crossing"), default=False)
    correct_norm_hours_last_month_acc_period = models.BooleanField(
        default=False, verbose_name=_('Корректировать норму часов для последнего месяца уч. периода (если уч. период != 1 мес)'),
        help_text='Используется при разделении табеля на осн. и доп. Т.е. норма за последний месяц уч. периода = '
                  '{норма по произв. календарю за уч. период} - {отработанные часы за прошлые месяцы}.')
    clean_wdays_on_employment_dt_change = models.BooleanField(
        default=False, verbose_name=_('Clean worker days on employment date change'),
    )
    create_employment_on_set_or_update_director_code = models.BooleanField(
        default=False,
        verbose_name=_('Create employment on set or update director code'),
    )
    crop_work_hours_by_shop_schedule = models.BooleanField(
        default=False, verbose_name=_('Crop work hours by shop schedule')
    )
    descrease_employment_dt_fired_in_api = models.BooleanField(
        default=False, verbose_name=_('Descrease employment date fired in api'),
        help_text=_('Relevant for data received via the api'),
    )
    display_chart_in_other_stores = models.BooleanField(
        default=False,
        verbose_name=_('Ability to disconnect to an account in the charts of other stores')
    )
    download_tabel_template = models.CharField(
        max_length=64, verbose_name=_('Download tabel template'),
        choices=TABEL_FORMAT_CHOICES, default='default',
    )
    edit_manual_fact_on_recalc_fact_from_att_records = models.BooleanField(
        default=False,
        verbose_name='Изменять ручные корректировки при пересчете факта на основе отметок (при подтверждения плана)',
    )
    enable_camera_ticks = models.BooleanField(
        default=False, verbose_name=_('Enable camera ticks'))
    exchange_settings = models.ForeignKey(
        'timetable.ExchangeSettings',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_('Default exchange settings'),
        related_name='networks',
    )
    fines_settings = models.TextField(default='{}', verbose_name=_('Fines settings')) # Fines will be calculated during fact hours calculation, example at src.timetable.tests.test_main.TestFineLogic
    fiscal_sheet_divider_alias = models.CharField(
        max_length=64, choices=FISCAL_SHEET_DIVIDERS_ALIAS_CHOICES, null=True, blank=True,
        verbose_name='Алгоритм разделения табеля', 
        help_text='Если не указано, то при расчете табеля разделение на осн. и доп. не производится')
    forbid_edit_employments_came_through_integration = models.BooleanField(
        default=True, verbose_name='Запрещать редактировать трудоустройства, пришедшие через интеграцию',
        help_text='У которых code не пустой',
    )
    get_position_from_work_type_name_in_calc_timesheet = models.BooleanField(
        default=False,
        verbose_name='Получать должность по типу работ при формировании фактического табеля',
    )
    ignore_parent_code_when_updating_department_via_api = models.BooleanField(
        default=False, verbose_name=_('Ignore parent code when updating department via api'),
        help_text=_('It must be enabled for cases when the organizational structure is maintained manually'),
    )
    ignore_shop_code_when_updating_employment_via_api = models.BooleanField(
        default=False, verbose_name='Не учитывать shop_code при изменении трудоустройства через api',
        help_text='Необходимо включить для случаев, когда привязка трудоустройств к отделам поддерживается вручную',
    )
    load_template = models.ForeignKey(
        'forecast.LoadTemplate',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_('Default load template'),
        related_name='networks',
    )
    max_plan_diff_in_seconds = models.PositiveIntegerField(
        verbose_name=_('Max difference between the start or end time to "pull" to the planned work day'),
        default=3600 * 7,
    )
    max_work_shift_seconds = models.PositiveIntegerField(
        verbose_name=_('Maximum shift length (in seconds)'), default=3600 * 16)
    need_symbol_for_vacancy = models.BooleanField(default=False, verbose_name=_('Need symbol for vacancy')) # Whether the worker identificator is needed, to apply for a vacancy
    okpo = models.CharField(blank=True, null=True, max_length=15, verbose_name=_('OKPO code'))
    only_fact_hours_that_in_approved_plan = models.BooleanField(
        default=False,
        verbose_name=_('Count only fact hours that in approved plan'),
    )
    prev_months_work_hours_source = models.PositiveSmallIntegerField(
        verbose_name='Источник рабочих часов за пред. месяцы уч. периода',
        choices=PREV_MONTHS_WORK_HOURS_SOURCE_CHOICES, default=WD_FACT_APPROVED)
    # Doesn't seem to be used anywhere, probably the logic changed and setting was left here.
    # run_recalc_fact_from_att_records_on_plan_approve = models.BooleanField(
    #     default=True, verbose_name=_('Run recalculation of fact based on attendance records (ticks) on plan approve'),
    # )
    rebuild_timetable_min_delta = models.IntegerField(default=2, verbose_name='Минимальное время для составления графика')
    round_work_hours_alg = models.PositiveSmallIntegerField(
        null=True, blank=True,
        choices=ROUND_WORK_HOURS_ALG_CHOICES,
        verbose_name='Алгоритм округления рабочих часов',
    )
    set_closest_plan_approved_delta_for_manual_fact = models.PositiveIntegerField(
        verbose_name='Макс. разница времени начала и времени окончания в факте и в плане '
                     'при проставлении ближайшего плана в ручной факт (в секундах)',
        default=60 * 60 * 5,
    )
    shop_default_values = models.TextField(verbose_name=_('Shop default values'), default='{}')
    show_checkbox_for_inspection_version = models.BooleanField(
        default=True,
        verbose_name=_('Show checkbox for downloading inspection version of timetable')
    )
    show_closed_shops_gap = models.PositiveIntegerField(default=30,  verbose_name=_('Show closed shops in shop tree for N days'))
    show_cost_for_inner_vacancies = models.BooleanField(
        verbose_name='Отображать поле "стоимость работ" для внутренних вакансий',
        default=False
    )
    show_user_biometrics_block = models.BooleanField(
        default=False,
        verbose_name=_('Show user biometrics block'),
    )
    show_worker_day_additional_info = models.BooleanField(
        default=False, verbose_name=_('Show worker day additional info'),
        help_text=_('Displaying information about who last edited a worker day and when, when hovering over the corner'))
    show_worker_day_tasks = models.BooleanField(
        default=False, verbose_name=_('Show worker day tasks'))
    skip_leaving_tick = models.BooleanField(
        verbose_name=_('Skip the creation of a departure mark if more than '
                       'the Maximum shift length has passed since the opening of the previous shift'),
        default=False,
    )
    timesheet_max_hours_threshold = models.DecimalField(
        verbose_name='Максимальное количество часов в белом табеле', default=Decimal('12.00'), max_digits=5, decimal_places=2)
    timesheet_min_hours_threshold = models.CharField(
        verbose_name='Минимальное количество часов в белом табеле', max_length=64, default='4.00', 
        help_text='Может принимать либо числовое значение, либо название функции')
    timesheet_divider_sawh_hours_key = models.CharField(max_length=128, default='curr_month')
    timetable_format = models.CharField(
        max_length=64, verbose_name=_('Timetable format'),
        choices=TIMETABLE_FORMAT_CHOICES, default='cell_format',
    )
    trust_tick_request = models.BooleanField(
        verbose_name=_('Create attendance record without check photo.'),
        default=False,
    )
    use_internal_exchange = models.BooleanField(
        default=True,
        verbose_name=_('Use internal exchange'),
        help_text=_('Regulates the action on the vacancy due to the exchange or natural')
    )
    worker_position_default_values = models.TextField(verbose_name=_('Worker position default values'), default='{}') #default values for newly created WorkerPosition, example at src.base.tests.test_worker_position.TestSetWorkerPositionDefaultsModel


    ANALYTICS_TYPE_METABASE = 'metabase'
    ANALYTICS_TYPE_CUSTOM_IFRAME = 'custom_iframe'
    ANALYTICS_TYPE_POWER_BI_EMBED = 'power_bi_embed'
    ANALYTICS_TYPE_CHOICES = (
        (ANALYTICS_TYPE_METABASE, 'Метабейз'),
        (ANALYTICS_TYPE_CUSTOM_IFRAME, 'Кастомный iframe (из json настройки analytics_iframe)'),
        (ANALYTICS_TYPE_POWER_BI_EMBED, 'Power BI через получение embed токена'),
    )
    analytics_type = models.CharField(
        verbose_name='Вид аналитики', max_length=32, choices=ANALYTICS_TYPE_CHOICES, default=ANALYTICS_TYPE_METABASE)

    tracker = FieldTracker(fields=('accounting_period_length', 'timesheet_min_hours_threshold'))

    @property
    def settings_values_prop(self):
        return json.loads(self.settings_values)

    @tracker
    def save(self, *args, **kwargs):
        if self.id and self.tracker.has_changed('accounting_period_length'):
            cache.delete_pattern("prod_cal_*_*_*")
        if self.tracker.has_changed('timesheet_min_hours_threshold'):
            self.get_timesheet_min_hours_threshold(100)
        return super().save(*args, **kwargs)


    def get_timesheet_min_hours_threshold(self, work_hours):
        try:
            min_hours_threshold_func = getattr(min_threshold_funcs, self.timesheet_min_hours_threshold, None)
            if min_hours_threshold_func:
                return min_hours_threshold_func(work_hours)
            else:
                return Decimal(self.timesheet_min_hours_threshold)
        except:
            raise ValueError(
                _('timesheet_min_hours_threshold can take either a numerical value or a function name')
            )

    def set_settings_value(self, k, v, save=False):
        settings_values = json.loads(self.settings_values)
        settings_values[k] = v
        self.settings_values = json.dumps(settings_values)
        if save:
            self.save()

    def get_department(self):
        return None

    @cached_property
    def position_default_values(self):
        return json.loads(self.worker_position_default_values)

    @cached_property
    def fines_settings_values(self):
        return json.loads(self.fines_settings)

    @cached_property
    def night_edges(self):
        return self.settings_values_prop.get('night_edges', Network.DEFAULT_NIGHT_EDGES)

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

    def clean(self):
        if self.analytics_type == Network.ANALYTICS_TYPE_CUSTOM_IFRAME:
            analytics_iframe = self.settings_values_prop.get('analytics_iframe')
            if not analytics_iframe:
                raise DjangoValidationError(_('It is necessary to fill in analytics_iframe in the settings values'))


class NetworkConnect(AbstractActiveModel):
    class Meta:
        verbose_name = 'Связь сетей'
        verbose_name_plural = 'Связи сетей'

    client = models.ForeignKey(Network, related_name='outsourcing_connections', on_delete=models.PROTECT)
    outsourcing = models.ForeignKey(Network, related_name='outsourcing_clients', on_delete=models.PROTECT)
    allow_assign_employements_from_outsource = models.BooleanField(default=False, verbose_name='Разрешить назначать сотрудников из аутсорс сетей')
    allow_choose_shop_from_client_for_employement = models.BooleanField(default=False, verbose_name='Разрешить выбирать магазин для сотрудника из сети клиента')


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


class ShopQuerySet(QuerySet):
    def delete(self):
        with Shop._deletion_context():
            self._not_support_combined_queries('delete')
            assert not self.query.is_sliced, \
                "Cannot use 'limit' or 'offset' with delete."

            if self.query.distinct or self.query.distinct_fields:
                raise TypeError('Cannot call delete() after .distinct().')
            if self._fields is not None:
                raise TypeError("Cannot call delete() after .values() or .values_list()")

            del_query = self._chain()
            del_query._for_write = True

            # Disable non-supported fields.
            del_query.query.select_for_update = False
            del_query.query.select_related = False
            del_query.query.clear_ordering(force_empty=True)

            collector = Collector(using=del_query.db)
            collector.collect(del_query)
            self.update(dttm_deleted=timezone.now())


class ShopManager(TreeManager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(dttm_deleted__date__gt=timezone.now().date()) | models.Q(dttm_deleted__isnull=True)
        )


class Shop(MPTTModel, AbstractActiveNetworkSpecificCodeNamedModel):
    """Shop/department"""
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
    load_template_settings = models.TextField(default='{}')
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

    objects = ShopManager.from_queryset(ShopQuerySet)()
    objects_with_excluded = TreeManager.from_queryset(ShopQuerySet)()

    tracker = FieldTracker(
        fields=['tm_open_dict', 'tm_close_dict', 'load_template', 'latitude', 'longitude', 'fias_code', 'director_id',
                'region_id', 'timezone'])

    def __str__(self):
        return '{}, {}, {}'.format(
            self.name,
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

    @property
    def load_settings(self):
        return json.loads(self.load_template_settings)

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
                        dt_fired=datetime.date(3999, 1, 1),
                        norm_work_hours=0,
                    )
                )

    @cached_property
    def shop_default_values_dict(self):
        shop_default_values = json.loads(self.network.shop_default_values)
        if shop_default_values:
            for re_pattern, shop_default_values_by_name_dict in shop_default_values.items():
                if re.search(re_pattern, str(self.level), re.IGNORECASE):
                    for re_pattern, shop_default_values_dict in shop_default_values_by_name_dict.items():
                        if re.search(re_pattern, self.name, re.IGNORECASE):
                            return shop_default_values_dict

    def _set_shop_defaults(self):
        if self.shop_default_values_dict:
            wtn_codes_with_otn_codes = self.shop_default_values_dict.get('wtn_codes_with_otn_codes')
            if wtn_codes_with_otn_codes:
                from src.timetable.models import WorkTypeName, WorkType
                from src.forecast.models import OperationTypeName, OperationType
                for wtn_code, otn_code in wtn_codes_with_otn_codes:
                    work_type = None
                    if wtn_code:
                        wtn = WorkTypeName.objects.filter(
                            network_id=self.network_id, code=wtn_code).first()
                        if wtn:
                            work_type, _wt_created = WorkType.objects.get_or_create(
                                shop=self, work_type_name=wtn)
                    if otn_code:
                        otn = OperationTypeName.objects.filter(
                            network_id=self.network_id, code=otn_code).first()
                        if otn:
                            _op_type, _ot_created = OperationType.objects.get_or_create(
                                shop=self,
                                operation_type_name=otn,
                                defaults=dict(
                                    work_type=work_type,
                                )
                            )

    @tracker
    def save(self, *args, force_create_director_employment=False, force_set_defaults=False, **kwargs):
        is_new = self.id is None

        forecast_step = self.forecast_step_minutes
        if isinstance(forecast_step, str):
            forecast_step = parse(forecast_step)
        
        if forecast_step.hour == 0 and forecast_step.minute == 0:
            raise ValidationError(_("Forecast step can't be 0."))

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
        timezone_changed = self.tracker.has_changed('timezone')
        if not is_new and timezone_changed:
            transaction.on_commit(lambda: cache.delete(f'shop_tz_offset:{self.id}'))

        if load_template_changed and self.load_template_status == self.LOAD_TEMPLATE_PROCESS:
            raise ValidationError(_('It is not possible to change the load template as it is in the calculation process.'))

        res = super().save(*args, **kwargs)
        if is_new:
            transaction.on_commit(self._handle_new_shop_created)
        elif self.tracker.has_changed('tm_open_dict') or self.tracker.has_changed('tm_close_dict'):
            transaction.on_commit(self._handle_schedule_change)
        
        if is_new and self.load_template_id is None:
            from src.forecast.models import LoadTemplate
            lt = self.network.load_template_id
            if self.shop_default_values_dict and self.shop_default_values_dict.get('load_template'):
                lt = LoadTemplate.objects.filter(code=self.shop_default_values_dict.get('load_template')).first()
                if not lt:
                    raise ValidationError(_('There is not load template with code {}.').format(self.shop_default_values_dict.get('load_template')))
                lt = lt.id
            if lt:
                self.load_template_id = lt
                load_template_changed = True

        if load_template_changed and not (self.load_template_id is None):
            from src.forecast.load_template.utils import apply_load_template
            from src.forecast.load_template.tasks import calculate_shops_load
            apply_load_template(self.load_template_id, self.id)
            if not is_new:
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

        if is_new or force_set_defaults:
            self._set_shop_defaults()

        if not is_new and self.tracker.has_changed('region_id'):
            transaction.on_commit(lambda: cache.delete_pattern("prod_cal_*_*_*"))

        return res

    def get_exchange_settings(self):
        return self.exchange_settings or self.network.exchange_settings

    def get_tz_offset(self):
        if self.timezone:
            offset = int(self.timezone.utcoffset(datetime.datetime.now()).seconds / 3600)
        else:
            offset = settings.CLIENT_TIMEZONE

        return offset

    @classmethod
    def get_cached_tz_offset_by_shop_id(cls, shop_id):
        # ключ shop_tz_offset:{shop_id}, значение Moscow/Europe
        k = f'shop_tz_offset:{shop_id}'
        cached_timezone = cache.get(k)
        if not cached_timezone:
            timezone = Shop.objects.filter(id=shop_id).values_list('timezone', flat=True).first()
            if timezone:
                cache.set(k, timezone)
        else:
            timezone = cached_timezone
        if timezone:
            offset = int(timezone.utcoffset(datetime.datetime.now()).seconds / 3600)
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
    
    @staticmethod
    def _deletion_context():
        from src.timetable.models import WorkerDay, WorkerConstraint
        return OverrideBaseManager([Employment, WorkerDay, WorkerConstraint])

    def delete(self, using=None, keep_parents=False):
        with self._deletion_context():
            using = using or router.db_for_write(self.__class__, instance=self)
            assert self.pk is not None, (
                "%s object can't be deleted because its %s attribute is set to None." %
                (self._meta.object_name, self._meta.pk.attname)
            )

            collector = Collector(using=using)
            collector.collect([self], keep_parents=keep_parents)
            self.dttm_deleted = timezone.now()
            self.save()
        return self


class EmploymentManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(dttm_deleted__date__gt=timezone.now().date()) | models.Q(dttm_deleted__isnull=True)
        )

    def annotate_main_work_type_id(self):
        from src.timetable.models import EmploymentWorkType
        return self.annotate(
            main_work_type_id=Subquery(
                EmploymentWorkType.objects.filter(
                    employment_id=OuterRef('id'),
                    priority=1,
                ).values('work_type_id')[:1]
            )
        )

    def get_active(self, network_id=None, dt_from=None, dt_to=None, extra_q=None, annotate_main_work_type_id=False, **kwargs):
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
                models.Q(shop__network_id=network_id) |
                models.Q(employee__user__network_id=network_id)
            )
        if extra_q:
            q &= extra_q
        
        queryset = self

        if annotate_main_work_type_id:
            queryset = self.annotate_main_work_type_id()

        return queryset.filter(q, **kwargs)

    def get_active_empl_by_priority(  # TODO: переделать, чтобы можно было в 1 запросе получать активные эмплойменты для пар (сотрудник, даты)?
            self, network_id=None, dt=None, dt_from=None, dt_to=None, priority_shop_id=None, priority_employment_id=None,
            priority_work_type_id=None, priority_by_visible=True, extra_q=None, priority_shop_network_id=None, **kwargs):
        assert dt or (dt_from and dt_to)
        dt_from = dt or dt_from
        dt_to = dt or dt_to
        qs = self.get_active(network_id=network_id, dt_from=dt_from, dt_to=dt_to, extra_q=extra_q, **kwargs)

        order_by = []
        if priority_by_visible:
            order_by.append('-is_visible')

        if priority_shop_network_id:
            qs = qs.annotate_value_equality(
                'is_equal_shop_networks', 'shop__network_id', priority_shop_network_id,
            )
            order_by.append('-is_equal_shop_networks')

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

    CHOICE_ALLOWED_TABS = [
        ('load_forecast', 'Прогноз потребностей'),
        ('schedule', 'Расписание'),
        ('employees', 'Сотрудники'),
        ('shift_exchange', 'Биржа смен'),
        ('analytics', 'Аналитика'), 
        ('settings', 'Настройки'),
    ]

    dttm_modified = models.DateTimeField(blank=True, null=True)
    subordinates = models.ManyToManyField("self", blank=True, symmetrical=False)
    has_perm_to_change_protected_wdays = models.BooleanField(
        default=False, verbose_name='Может изменять/подтверждать "защищенные" рабочие дни')
    has_perm_to_approve_other_shop_days = models.BooleanField(
        default=False, verbose_name='Может подтверждать дни из других подразделений')

    allowed_tabs = MultipleChoiceField(choices=CHOICE_ALLOWED_TABS)

    def __str__(self):
        return '{}, {}, {}'.format(
            self.id,
            self.name,
            self.code,
            # ', '.join(list(self.subordinates.values_list('name', flat=True)))
        )

    @classmethod
    def check_has_perm_to_group(cls, user, group=None, groups=[]):
        group_perm = True
        if any(groups) or group:
            groups = groups or [group,]
            group_perm = cls.objects.filter(
                Q(employments__employee__user=user) | Q(workerposition__employment__employee__user=user),
                subordinates__id__in=groups,
            ).exists()

        return group_perm
    
    @classmethod
    def get_subordinated_group_ids(cls, user):
        return list(cls.objects.filter(id__in=user.get_group_ids()).values_list('subordinates__id', flat=True).distinct())

    @classmethod
    def check_has_perm_to_edit_group_objects(cls, group_from, group_to, user):
        if not (cls.check_has_perm_to_group(user, group=group_from) and cls.check_has_perm_to_group(user, group=group_to)):
            raise PermissionDenied()


class ProductionDay(AbstractModel):
    """День из производственного календаря короч."""

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
    def get_prod_days_for_region(cls, region_id, **kwargs):
        q = Q(
            Q(region_id=region_id) | Q(region__children__id=region_id),
            **kwargs,
        )
        prod_cal_subq = cls.objects.filter(q, dt=OuterRef('dt')).annotate(
            is_equal_regions=Case(
                When(region_id=Value(region_id), then=True),
                default=False, output_field=models.BooleanField()
            ),
        ).order_by('-is_equal_regions')
        return cls.objects.filter(
            q,
            id=Subquery(prod_cal_subq.values_list('id', flat=True)[:1])
        ).distinct()

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

    def save(self, *args, **kwargs):
        cache.delete_pattern("prod_cal_*_*_*")
        return super().save(*args, **kwargs)


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
    first_name = models.CharField(blank=True, max_length=30, verbose_name='first name')
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
    ldap_login = models.CharField(max_length=150, null=True, blank=True)

    def get_fio(self):
        """
        :return: Фамилия Имя Отчество (если есть)
        """
        fio = f'{self.last_name} {self.first_name or ""}'
        if self.middle_name:
            fio += f' {self.middle_name}'
        return fio

    def get_short_fio(self):
        """
        :return: Фамилия с инициалами
        """
        short_fio = f'{self.last_name}'
        if self.first_name:
            short_fio += f' {self.first_name[0].upper()}.'
        if self.middle_name:
            short_fio += f'{self.middle_name[0].upper()}.'
        return short_fio

    @property
    def short_fio(self):
        return self.get_short_fio()

    @property
    def fio(self):
        return self.get_fio()

    def get_active_employments(self, shop_id=None, dt_from=None, dt_to=None):
        q = Q(
            Q(employee__user__network_id=self.network_id) |
            Q(shop__network_id=self.network_id)
        )
        if shop_id:
            q &= Q(
                shop__in=Shop.objects.get_queryset_ancestors(
                    queryset=Shop.objects.filter(id=shop_id),
                    include_self=True,
                )
            )
        kwargs = {}
        if dt_from:
            kwargs['dt_from'] = dt_from
        if dt_to:
            kwargs['dt_to'] = dt_to
        return Employment.objects.get_active(
            employee__user=self,
            extra_q=q,
            **kwargs
        )
    
    def get_shops(self, include_descendants=False):
        shops = Shop.objects.filter(id__in=self.get_active_employments().values_list('shop_id', flat=True))
        if include_descendants:
            shops = Shop.objects.get_queryset_descendants(shops, include_self=True)
        return shops

    def get_group_ids(self, shop_id=None):
        groups = self.get_active_employments(shop_id=shop_id).values_list('position__group_id', 'function_group_id')
        return list(set(list(map(lambda x: x[0], groups)) + list(map(lambda x: x[1], groups))))

    def save(self, *args, **kwargs):
        if not self.password and isinstance(self.username, str) and settings.SET_USER_PASSWORD_AS_LOGIN:
            self.set_password(self.username)
        super().save(*args, **kwargs)
        self.compress_image()

    def compress_image(self, quality: int = settings.AVATAR_QUALITY):
        if self.avatar:
            return images.compress_image(self.avatar.path, quality)

    def get_subordinates(
        self,
        dt=None,
        user_shops=None,
        user_subordinated_group_ids=None,
        dt_to_shift=None,
        network_id=None
    ):
        """Choice of employees who report to me."""
        if network_id and not user_shops:
            user_shops = Shop.objects.filter(network_id=network_id).values_list('id', flat=True)
        if not user_shops:
            user_shops = self.get_shops(include_descendants=True).values_list('id', flat=True)
        if not user_subordinated_group_ids:
            user_subordinated_group_ids = Group.get_subordinated_group_ids(self)
        dt_to = dt
        if dt_to_shift and dt_to:
            dt_to += dt_to_shift
        return Employee.objects.annotate(
            is_subordinate=models.Exists(
                Employment.objects.get_active(
                    extra_q=models.Q(position__group_id__in=user_subordinated_group_ids) |
                            models.Q(function_group_id__in=user_subordinated_group_ids) |
                            (models.Q(function_group_id__isnull=True) & models.Q(position__group__isnull=True)),
                    dt_from=dt,
                    dt_to=dt_to,
                    employee_id=OuterRef('id'),
                    shop_id__in=user_shops,
                )
            )
        ).filter(is_subordinate=True)


class AllowedSawhSetting(AbstractModel):
    position = models.ForeignKey('base.WorkerPosition', on_delete=models.CASCADE)
    sawh_settings = models.ForeignKey('base.SAWHSettings', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Разрешенная настройки нормы часов'
        verbose_name_plural = 'Разрешенные настройки нормы часов'


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
    sawh_settings = models.ForeignKey(
        to='base.SAWHSettings',
        on_delete=models.PROTECT,
        verbose_name='Настройка нормы',
        null=True, blank=True,
        related_name='positions',
    )
    allowed_sawh_settings = models.ManyToManyField(
        'base.SAWHSettings', through='base.AllowedSawhSetting', blank=True)
    tracker = FieldTracker(fields=['hours_in_a_week'])

    def __str__(self):
        return '{}, {}'.format(self.name, self.id)

    @cached_property
    def wp_defaults(self):
        wp_defaults_dict = self.network.position_default_values
        if wp_defaults_dict:
            for re_pattern, wp_defaults in wp_defaults_dict.items():
                if re.search(re_pattern, self.name, re.IGNORECASE):
                    return wp_defaults

    @cached_property
    def wp_fines(self):
        wp_fines_dict = self.network.fines_settings_values if self.network else None
        if wp_fines_dict:
            for re_pattern, wp_fines in wp_fines_dict.items():
                if re.search(re_pattern, self.name, re.IGNORECASE):
                    return wp_fines

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

    @tracker
    def save(self, *args, force_set_defaults=False, **kwargs):
        is_new = self.id is None
        if is_new or force_set_defaults:
            self._set_plain_defaults()
        res = super(WorkerPosition, self).save(*args, **kwargs)
        if is_new or force_set_defaults:
            self._set_m2m_defaults()
        if not is_new and self.tracker.has_changed('hours_in_a_week'):
            cache.delete_pattern("prod_cal_*_*_*")
        return res

    def get_department(self):
        return None


class EmploymentQuerySet(AnnotateValueEqualityQSMixin, QuerySet):
    def last_hired(self):
        last_hired_subq = self.filter(user_id=OuterRef('user_id')).order_by('-dt_hired').values('id')[:1]
        return self.filter(
            id=Subquery(last_hired_subq)
        )

    def delete(self):
        from src.timetable.models import WorkerDay
        from src.timetable.worker_day.tasks import clean_wdays
        from src.timetable.timesheet.tasks import recalc_timesheet_on_data_change
        with transaction.atomic():
            wdays_ids = list(WorkerDay.objects.filter(employment__in=self).values_list('id', flat=True))
            WorkerDay.objects.filter(employment__in=self).update(employment_id=None)
            deleted_count = self.update(dttm_deleted=timezone.now())
            transaction.on_commit(lambda: clean_wdays.delay(id__in=wdays_ids))
            dt_now = timezone.now().date()
            recalc_timesheet_on_data_change(
                {
                    e.employee_id: [dt_now.replace(day=1) - datetime.timedelta(1), dt_now] 
                    for e in self
                }
            )
        return deleted_count, {'base.Employment': deleted_count}


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
        return '{}, {}, {}, {}, {}'.format(self.id, self.shop, self.employee, self.dt_hired, self.dt_fired)

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=128, null=True, blank=True, unique=True)
    employee = models.ForeignKey('base.Employee', on_delete=models.CASCADE, related_name="employments")
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
    is_visible = models.BooleanField(default=True, verbose_name=_('Display in the chart of my shop'))
    is_visible_other_shops = models.BooleanField(default=True, verbose_name=_('Display in the chart of other shops'))

    sawh_settings = models.ForeignKey(
        to='base.SAWHSettings',
        on_delete=models.PROTECT,
        verbose_name=_('Sawh settings'),
        null=True, blank=True,
        related_name='employments',
    )

    tracker = FieldTracker(fields=['position', 'dt_hired', 'dt_fired', 'norm_work_hours', 'shop_id', 'sawh_settings_id', 'dttm_deleted'])

    objects = EmploymentManager.from_queryset(EmploymentQuerySet)()
    objects_with_excluded = models.Manager.from_queryset(EmploymentQuerySet)()

    def has_permission(self, permission, method='GET'):
        groups = [self.function_group, self.position.group if self.position else None]
        if not any(groups):
            raise ValidationError(_('Unable to define worker access group. Assign an access group to him or a position associated with an access group.'))
        return FunctionGroup.objects.filter(
            func=permission,
            method=method,
            group__in=filter(None, groups),
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
        from src.integration.tasks import export_or_delete_employment_zkteco
        from src.timetable.timesheet.tasks import recalc_timesheet_on_data_change
        with transaction.atomic():
            wdays_ids = list(WorkerDay.objects.filter(employment=self).values_list('id', flat=True))
            WorkerDay.objects.filter(employment=self).update(employment_id=None)
            if self.employee.user.network.clean_wdays_on_employment_dt_change:
                transaction.on_commit(lambda: clean_wdays.delay(id__in=wdays_ids))
            res = super(Employment, self).delete(**kwargs)
            if settings.ZKTECO_INTEGRATION:
                transaction.on_commit(lambda: export_or_delete_employment_zkteco.delay(self.id))
            transaction.on_commit(lambda: cache.delete_pattern(f"prod_cal_*_*_{self.employee_id}"))
            dt_now = timezone.now().date()
            recalc_timesheet_on_data_change({self.employee_id: [dt_now.replace(day=1) - datetime.timedelta(1), dt_now]})
            return res

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

    @tracker
    def save(self, *args, **kwargs):
        from src.integration.tasks import export_or_delete_employment_zkteco
        if hasattr(self, 'shop_code'):
            self.shop = Shop.objects.get(code=self.shop_code)
        if hasattr(self, 'username'):
            self.employee, _employee_created = Employee.objects.get_or_create(
                user=User.objects.get(username=self.username), tabel_code=self.tabel_code)
        if hasattr(self, 'position_code'):
            self.position = WorkerPosition.objects.get(code=self.position_code)

        force_create_work_types = kwargs.pop('force_create_work_types', False)
        is_new = self.pk is None
        recreated_from_deleted = self.tracker.has_changed('dttm_deleted') and self.dttm_deleted is None    # for AbstractActiveModel "new" can also be an updated record from DB that had `dttm_deleted`
        position_has_changed = self.tracker.has_changed('position')
        res = super().save(*args, **kwargs)
        # при создании трудоустройства или при смене должности проставляем типы работ по умолчанию
        if force_create_work_types or is_new or position_has_changed:
            self.create_or_update_work_types([self])

        # при смене должности пересчитываем рабочие часы в будущем
        if not is_new and position_has_changed:
            self.recalc_future_worker_days([self.id])

        if (is_new or recreated_from_deleted or (self.tracker.has_changed('dt_hired') or self.tracker.has_changed('dt_fired'))) and \
                self.employee.user.network and self.employee.user.network.clean_wdays_on_employment_dt_change:
            from src.timetable.worker_day.tasks import clean_wdays
            from src.util.models_converter import Converter
            kwargs = {}
            if is_new:
                kwargs = {
                    'employee_id': self.employee_id,
                }
                if self.dt_hired:
                    kwargs['dt__gte'] = Converter.convert_date(self.dt_hired)
                if self.dt_fired:
                    kwargs['dt__lt'] = Converter.convert_date(self.dt_fired)
            else:
                prev_dt_hired = self.tracker.previous('dt_hired')
                if prev_dt_hired and prev_dt_hired < self.dt_hired:
                    dt__gte = prev_dt_hired
                else:
                    dt__gte = self.dt_hired
                kwargs = {
                    'employee_id': self.employee_id,
                    'dt__gte': Converter.convert_date(dt__gte),
                }
            transaction.on_commit(lambda: clean_wdays.delay(**kwargs))

        if (is_new or self.tracker.has_changed('dt_hired') or self.tracker.has_changed('dt_fired') or self.tracker.has_changed('shop_id')) and settings.ZKTECO_INTEGRATION:
            transaction.on_commit(lambda: export_or_delete_employment_zkteco.delay(self.id, prev_shop_id=(self.tracker.previous('shop_id') if self.tracker.has_changed('shop_id') else None)))

        if (is_new
                or self.tracker.has_changed('dt_hired')
                or self.tracker.has_changed('dt_fired')
                or position_has_changed
                or self.tracker.has_changed('norm_work_hours')
                or self.tracker.has_changed('sawh_settings_id')):
            transaction.on_commit(lambda: cache.delete_pattern(f"prod_cal_*_*_{self.employee_id}"))
            if not is_new:
                from src.timetable.timesheet.tasks import recalc_timesheet_on_data_change
                dt_now = timezone.now().date()
                recalc_timesheet_on_data_change({self.employee_id: [dt_now.replace(day=1) - datetime.timedelta(1), dt_now]})

        return res

    def is_active(self, dt=None):
        dt = dt or timezone.now().date()
        return (self.dt_hired is None or self.dt_hired <= dt) and (self.dt_fired is None or self.dt_fired >= dt)
    
    @staticmethod
    def create_or_update_work_types(employments):
        from src.timetable.models import EmploymentWorkType, WorkType
        with transaction.atomic():
            default_work_types = {}

            for employment in employments:
                default_work_types.setdefault(employment.position_id, {}).setdefault(employment.shop_id, [])

            work_type_names = WorkerPosition.default_work_type_names.through.objects.filter(
                workerposition_id__in=default_work_types.keys(),
            ).values_list('worktypename_id', 'workerposition_id')


            for work_type_name_id, position_id in work_type_names:
                for shop_id in default_work_types[position_id].keys():
                    work_type, _wt_created = WorkType.objects.get_or_create(
                        shop_id=shop_id,
                        work_type_name_id=work_type_name_id,
                    )
                    default_work_types[position_id][shop_id].append(work_type)

            EmploymentWorkType.objects.filter(employment_id__in=map(lambda x: x.id, employments)).delete()
            EmploymentWorkType.objects.bulk_create(
                EmploymentWorkType(
                    employment_id=employment.id,
                    work_type=work_type,
                    priority=1 if i == 0 else 0,
                ) 
                for employment in employments
                for i, work_type in enumerate(default_work_types[employment.position_id][employment.shop_id])
            )

    @staticmethod
    def recalc_future_worker_days(employment_ids):
        from src.timetable.models import WorkerDay
        dt = datetime.date.today()
        for wd in WorkerDay.objects.filter(
                    employment_id__in=employment_ids,
                    is_fact=False,
                    dt__gt=dt,
                    type__is_dayoff=False,
                ).select_related(
                    'employment__position__breaks',
                    'shop__network__breaks',
                    'type',
                    'shop__settings__breaks',
                ):
            wd.save()

    @classmethod
    def _get_batch_delete_scope_fields_list(cls):
        return ['employee_id']

    @classmethod
    def _get_batch_update_manager(cls):
        return cls.objects_with_excluded

    @classmethod
    def _get_batch_delete_manager(cls):
        return cls.objects

    @classmethod
    def _get_batch_update_select_related_fields(cls):
        return ['employee__user__network', 'shop__network', 'position']

    @classmethod
    def _get_diff_lookup_fields(cls):
        return (
            'code',
            'shop__code',
            'employee__tabel_code',
            'position__code',
            'norm_work_hours',
            'dt_hired',
            'dt_fired',
        )

    @classmethod
    def _get_diff_headers(cls):
        return (
            'UIDзаписи',
            'КодПодразделения',
            'ТабельныйНомер',
            'КодДолжности',
            'Ставка',
            'ДатаНачалаРаботы',
            'ДатаОкончанияРаботы',
        )

    @classmethod
    def _get_diff_report_subject_fmt(cls):
        return 'Сверка трудоустройств от {dttm_now}'
    
    @classmethod
    def _post_batch(cls, **kwargs):
        """This function call after batch_update_or_create method."""
        from src.integration.tasks import export_or_delete_employment_zkteco
        from src.timetable.worker_day.tasks import clean_wdays
        from src.util.models_converter import Converter
        created_objs = kwargs.get('created_objs', [])
        updated_objs = kwargs.get('updated_objs', [])
        deleted_objs = kwargs.get('deleted_objs', [])
        before_update = kwargs.get('diff_data', {}).get('before_update', [])
        after_update = kwargs.get('diff_data', {}).get('after_update', [])

        employee_network = {
            e.id: e.user.network
            for e in Employee.objects.filter(
                id__in=list(map(lambda x: x.employee_id, created_objs)) + list(map(lambda x: x.employee_id, updated_objs))
            ).select_related('user__network')
        }

        employments_create_or_update_work_types = []
        employments_for_recalc_wh_in_future = []
        clean_wdays_kwargs = {
            'employee_id__in': [],
            'dt__gte': datetime.date.today(),
        }
        employees_for_clear_cache = set()
        zkteco_data = []
        created_employment: Employment
        for created_employment in created_objs:
            employments_create_or_update_work_types.append(created_employment)
            employees_for_clear_cache.add(created_employment.employee_id)
            if employee_network.get(created_employment.employee_id) and employee_network.get(created_employment.employee_id).clean_wdays_on_employment_dt_change:
                clean_wdays_kwargs['employee_id__in'].append(created_employment.employee_id)
                if created_employment.dt_hired:
                    clean_wdays_kwargs['dt__gte'] = min(clean_wdays_kwargs['dt__gte'], created_employment.dt_hired)
            if created_employment.sawh_settings_id is None and \
                    created_employment.position_id is not None and \
                    created_employment.position.sawh_settings_id is not None:
                Employment.objects.filter(pk=created_employment.pk).update(sawh_settings_id=created_employment.position.sawh_settings_id)

            if settings.ZKTECO_INTEGRATION:
                zkteco_data.append({'id': created_employment.id})

        for i, updated_employment in enumerate(updated_objs):
            shop_changed = before_update[i][1] != after_update[i][1]
            position_changed = before_update[i][3] != after_update[i][3]
            norm_work_hours_changed = before_update[i][4] != after_update[i][4]
            dt_hired_changed = before_update[i][5] != after_update[i][5]
            dt_fired_changed = before_update[i][6] != after_update[i][6]
            employee_id = updated_employment.employee_id

            if position_changed:
                employments_create_or_update_work_types.append(updated_employment)
                employments_for_recalc_wh_in_future.append(updated_employment.id)
            
            if (dt_hired_changed or dt_fired_changed) and employee_network.get(employee_id) and employee_network.get(employee_id).clean_wdays_on_employment_dt_change:
                clean_wdays_kwargs['employee_id__in'].append(employee_id)
                clean_wdays_kwargs['dt__gte'] = min(
                    clean_wdays_kwargs['dt__gte'], 
                    updated_employment.dt_hired or datetime.datetime.max,
                    before_update[i][5] or datetime.datetime.max,
                )
            if dt_hired_changed or dt_fired_changed or norm_work_hours_changed or position_changed:
                employees_for_clear_cache.add(employee_id)
            
            if (dt_hired_changed or dt_fired_changed or shop_changed) and settings.ZKTECO_INTEGRATION:
                zkteco_data.append({'id': updated_employment.id, 'prev_shop_code': before_update[i][1] if shop_changed else None})

        for deleted_employment in deleted_objs:
            employees_for_clear_cache.add(deleted_employment.employee_id)
            if employee_network.get(deleted_employment.employee_id) and employee_network.get(deleted_employment.employee_id).clean_wdays_on_employment_dt_change:
                clean_wdays_kwargs['employee_id__in'].append(deleted_employment.employee_id)
                if deleted_employment.dt_hired:
                    clean_wdays_kwargs['dt__gte'] = min(clean_wdays_kwargs['dt__gte'], deleted_employment.dt_hired)

            if settings.ZKTECO_INTEGRATION:
                zkteco_data.append({'id': deleted_employment.id})

        clean_wdays_kwargs['dt__gte'] = Converter.convert_date(clean_wdays_kwargs['dt__gte'])
        
        cls.create_or_update_work_types(employments_create_or_update_work_types)
        cls.recalc_future_worker_days(employments_for_recalc_wh_in_future)

        transaction.on_commit(
            lambda: clean_wdays.delay(
                **clean_wdays_kwargs,
            )
        )
        transaction.on_commit(
           lambda: [cache.delete_pattern(f"prod_cal_*_*_{e_id}") for e_id in employees_for_clear_cache]
        )
        transaction.on_commit(
            lambda: [export_or_delete_employment_zkteco.delay(data['id'], prev_shop_code=data.get('prev_shop_code')) for data in zkteco_data]
        )


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
        ('AttendanceRecords', 'Отметка (attendance_records)'),
        ('AttendanceRecords_report', 'Отчет по отметкам (Получить) (attendance_records/report/)'),
        ('AutoSettings_create_timetable', 'Составление графика (Создать) (auto_settings/create_timetable/)'),
        ('AutoSettings_set_timetable', 'Задать график (ответ от алгоритмов, Создать) (auto_settings/set_timetable/)'),
        ('AutoSettings_delete_timetable', 'Удалить график (Создать) (auto_settings/delete_timetable/)'),
        ('AuthUserView', 'Получить авторизованного пользователя (auth/user/)'),
        ('Break', 'Перерыв (break)'),
        ('ContentBlock', 'Блок контента (content_block)'),
        ('Employment', 'Трудоустройство (employment)'),
        ('Employee', 'Сотрудник (employee)'),
        ('Employee_shift_schedule', 'Графики смен сотрудников (employee/shift_schedule/)'),
        ('Employment_auto_timetable', 'Выбрать сорудников для автосоставления (Создать) (employment/auto_timetable/)'),
        ('Employment_timetable', 'Редактирование полей трудоустройства, связанных с расписанием (employment/timetable/)'),
        ('EmploymentWorkType', 'Связь трудоустройства и типа работ (employment_work_type)'),
        ('Employment_batch_update_or_create',
         'Массовое создание/обновление трудоустройств (Создать/Обновить) (employment/batch_update_or_create/)'),
        ('ExchangeSettings', 'Настройки обмена сменами (exchange_settings)'),
        ('FunctionGroupView', 'Доступ к функциям (function_group)'),
        ('FunctionGroupView_functions', 'Получить список доступных функций (Получить) (function_group/functions/)'),
        ('LoadTemplate', 'Шаблон нагрузки (load_template)'),
        ('LoadTemplate_apply', 'Применить шаблон нагрузки (Создать) (load_template/apply/)'),
        ('LoadTemplate_calculate', 'Рассчитать нагрузку (Создать) (load_template/calculate/)'),
        ('LoadTemplate_download', 'Скачать шаблон нагрузки (Получить) (load_template/download/)'),
        ('LoadTemplate_upload', 'Загрузить шаблон нагрузки (Создать) (load_template/upload/)'),
        ('MedicalDocumentType', 'Тип медицинского документа (medical_document_type)'),
        ('MedicalDocument', 'Период актуальности медицинского документа (medical_document)'),
        ('Network', 'Сеть (network)'),
        ('OperationTypeName', 'Название типа операции (operation_type_name)'),
        ('OperationType', 'Тип операции (operation_type)'),
        ('OperationTypeRelation', 'Отношение типов операций (operation_type_relation)'),
        ('OperationTypeTemplate', 'Шаблон типа операции (operation_type_template)'),
        ('PeriodClients', 'Нагрузка (timeserie_value)'),
        ('PeriodClients_indicators', 'Индикаторы нагрузки (Получить) (timeserie_value/indicators/)'),
        ('PeriodClients_put', 'Обновить нагрузку (Обновить) (timeserie_value/put/)'),
        ('PeriodClients_delete', 'Удалить нагрузку (Удалить) (timeserie_value/delete/)'),
        ('PeriodClients_upload', 'Загрузить нагрузку (Создать) (timeserie_value/upload/)'),
        ('PeriodClients_upload_demand', 'Загрузить нагрузку по магазинам (Создать) (timeserie_value/upload_demand/)'),
        ('PeriodClients_download', 'Скачать нагрузку (Получить) (timeserie_value/download/)'),
        ('Receipt', 'Чек (receipt)'),
        ('Reports_pivot_tabel', 'Скачать сводный табель (Получить) (report/pivot_tabel/)'),
        ('Reports_schedule_deviation', 'Скачать отчет по отклонениям от планового графика (Получить) (report/schedule_deviation/)'),
        ('Reports_consolidated_timesheet_report', 'Скачать "Консолидированный отчет об отработанном времени" (Получить) (report/consolidated_timesheet_report/)'),
        ('Reports_tick', 'Скачать "Отчёт об отметках сотрудников" (Получить) (report/tick/)'),
        ('Group', 'Группа доступа (group)'),
        ('SAWHSettings_daily', 'Получить данные по норме часов для каждого рабочего дня (Получить) (sawh_settings/daily)'),
        ('ShiftSchedule_batch_update_or_create', 'Массовое создание/обновление графиков работ (Создать/Обновить) (shift_schedule/batch_update_or_create/)'),
        ('ShiftScheduleInterval_batch_update_or_create', 'Массовое создание/обновление интервалов графиков работ сотрудников (Создать/Обновить) (shift_schedule/batch_update_or_create/)'),
        ('Shop', 'Отдел (department)'),
        ('Shop_stat', 'Статистика по отделам (Получить) (department/stat/)'),
        ('Shop_tree', 'Дерево отделов (Получить) (department/tree/)'),
        ('Shop_internal_tree', 'Дерево отделов сети пользователя (Получить) (department/internal_tree/)'),
        ('Shop_load_template', 'Изменить шаблон нагрузки магазина (Обновить) (department/{pk}/load_template/)'),
        ('Shop_outsource_tree', 'Дерево отделов клиентов (для аутсорс компаний) (Получить) (department/outsource_tree/)'),
        ('Task', 'Задача (task)'),
        ('TickPoint', 'Точка отметки (tick_points)'),
        ('Timesheet', 'Табель (timesheet)'),
        ('Timesheet_stats', 'Статистика табеля (Получить) (timesheet/stats/)'),
        ('Timesheet_recalc', 'Запустить пересчет табеля (Создать) (timesheet/recalc/)'),
        ('Timesheet_lines', 'Табель построчно (Получить) (timesheet/lines/)'),
        ('Timesheet_items', 'Сырые данные табеля (Получить) (timesheet/items/)'),
        ('User', 'Пользователь (user)'),
        ('User_change_password', 'Сменить пароль пользователю (Создать) (auth/password/change/)'),
        ('User_delete_biometrics', 'Удалить биометрию пользователя (Создать) (user/delete_biometrics/)'),
        ('User_add_biometrics', 'Добавить биометрию пользователя (Создать) (user/add_biometrics/)'),
        ('WorkerConstraint', 'Ограничения сотрудника (worker_constraint)'),
        ('WorkerDay', 'Рабочий день (worker_day)'),
        ('WorkerDay_approve', 'Подтвердить график (Создать) (worker_day/approve/)'),
        ('WorkerDay_daily_stat', 'Статистика по дням (Получить) (worker_day/daily_stat/)'),
        ('WorkerDay_worker_stat', 'Статистика по работникам (Получить) (worker_day/worker_stat/)'),
        ('WorkerDay_vacancy', 'Список вакансий (Получить) (worker_day/vacancy/)'),
        ('WorkerDay_change_list', 'Редактирование дней списоком (Создать) (worker_day/change_list)'),
        ('WorkerDay_copy_approved', 'Копировать рабочие дни из разных версий (Создать) (worker_day/copy_approved/)'),
        ('WorkerDay_copy_range', 'Копировать дни на следующий месяц (Создать) (worker_day/copy_range/)'),
        ('WorkerDay_duplicate', 'Копировать рабочие дни как ячейки эксель (Создать) (worker_day/duplicate/)'),
        ('WorkerDay_delete_worker_days', 'Удалить рабочие дни (Создать) (worker_day/delete_worker_days/)'),
        ('WorkerDay_exchange', 'Обмен сменами (Создать) (worker_day/exchange/)'),
        ('WorkerDay_exchange_approved', 'Обмен подтвержденными сменами (Создать) (worker_day/exchange_approved/)'),
        ('WorkerDay_confirm_vacancy', 'Откликнуться вакансию (Создать) (worker_day/confirm_vacancy/)'),
        ('WorkerDay_confirm_vacancy_to_worker', 'Назначить работника на вакансию (Создать) (worker_day/confirm_vacancy_to_worker/)'),
        ('WorkerDay_refuse_vacancy', 'Отказаться от вакансии (Создать) (worker_day/refuse_vacancy/)'),
        ('WorkerDay_reconfirm_vacancy_to_worker', 'Переназначить работника на вакансию (Создать) (worker_day/reconfirm_vacancy_to_worker/)'),
        ('WorkerDay_upload', 'Загрузить плановый график (Создать) (worker_day/upload/)'),
        ('WorkerDay_upload_fact', 'Загрузить фактический график (Создать) (worker_day/upload_fact/)'),
        ('WorkerDay_download_timetable', 'Скачать плановый график (Получить) (worker_day/download_timetable/)'),
        ('WorkerDay_download_tabel', 'Скачать табель (Получить) (worker_day/download_tabel/)'),
        ('WorkerDay_editable_vacancy', 'Получить редактируемую вакансию (Получить) (worker_day/{pk}/editable_vacancy/)'),
        ('WorkerDay_approve_vacancy', 'Подтвердить вакансию (Создать) (worker_day/{pk}/approve_vacancy/)'),
        ('WorkerDay_change_range', 'Создание/обновление дней за период (Создать) (worker_day/change_range/)'),
        ('WorkerDay_request_approve', 'Запросить подтверждение графика (Создать) (worker_day/request_approve/)'),
        ('WorkerDay_block', 'Заблокировать рабочий день (Создать) (worker_day/block/)'),
        ('WorkerDay_unblock', 'Разблокировать рабочий день (Создать) (worker_day/unblock/)'),
        ('WorkerDay_batch_block_or_unblock', 'Массово заблокировать/разблокировать рабочие дни (только в прошлом) (Создать) (worker_day/batch_block_or_unblock/)'),
        ('WorkerDay_generate_upload_example', 'Скачать шаблон графика (Получить) (worker_day/generate_upload_example/)'),
        ('WorkerDay_recalc', 'Пересчитать часы (Создать) (worker_day/recalc/)'),
        ('WorkerDay_overtimes_undertimes_report', 'Скачать отчет о переработках/недоработках (Получить) (worker_day/overtimes_undertimes_report/)'),
        ('WorkerDay_batch_update_or_create', 'Массовое создание/обновление дней сотрудников (Создать/Обновить) (worker_day/batch_update_or_create/)'),
        ('WorkerDayType', 'Тип дня сотрудника (worker_day_type)'),
        ('WorkerPosition', 'Должность (worker_position)'),
        ('WorkTypeName', 'Название типа работ (work_type_name)'),
        ('WorkType', 'Тип работ ()work_type'),
        ('WorkType_efficiency', 'Покрытие (Получить) (work_type/efficiency/)'),
        ('ShopMonthStat', 'Статистика по магазину на месяц (shop_month_stat)'),
        ('ShopMonthStat_status', 'Статус составления графика (Получить) (shop_month_stat/status/)'),
        ('ShopSettings', 'Настройки автосоставления (shop_settings)'),
        ('ShopSchedule', 'Расписание магазина (schedule)'),
        ('VacancyBlackList', 'Черный список для вакансий (vacancy_black_list)'),
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


class SawhSettingsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(dttm_deleted__date__gt=timezone.now().date()) | models.Q(dttm_deleted__isnull=True)
        )


class SawhSettingsQuerySet(QuerySet):
    def delete(self):
        self.update(dttm_deleted=timezone.now())


class SAWHSettings(AbstractActiveNetworkSpecificCodeNamedModel):
    """
    Настройки нормы часов.
    Модель нужна для распределения часов по месяцам в рамках учетного периода.
    """

    PART_OF_PROD_CAL_SUMM = 1
    FIXED_HOURS = 2
    SHIFT_SCHEDULE = 3

    SAWH_SETTINGS_TYPES = (
        (PART_OF_PROD_CAL_SUMM, 'Доля от суммы часов по произв. календарю в рамках уч. периода'),
        (FIXED_HOURS, 'Фикс. кол-во часов в месяц'),
        (SHIFT_SCHEDULE, 'Часы по графику смен'),
    )

    work_hours_by_months = models.JSONField(
        verbose_name='Настройки по распределению часов',
        null=True,
        blank=True,
    )  # Название ключей должно начинаться с m (например январь -- m1), чтобы можно было фильтровать через django orm
    type = models.PositiveSmallIntegerField(
        default=PART_OF_PROD_CAL_SUMM, choices=SAWH_SETTINGS_TYPES, verbose_name='Тип расчета')

    objects = SawhSettingsManager.from_queryset(SawhSettingsQuerySet)()
    objects_with_excluded = models.Manager.from_queryset(SawhSettingsQuerySet)()

    class Meta:
        verbose_name = 'Настройки нормы часов'
        verbose_name_plural = 'Настройки нормы часов'

    def __str__(self):
        return f'{self.name} {self.network.name}'


class SAWHSettingsMapping(AbstractModel):
    sawh_settings = models.ForeignKey('base.SAWHSettings', on_delete=models.CASCADE, verbose_name='Настройки СУРВ', related_name='mappings')
    year = models.PositiveSmallIntegerField(verbose_name='Год учетного периода', default=current_year)
    work_hours_by_months = models.JSONField(
        verbose_name='Настройки по распределению часов в рамках года',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Настройки нормы часов'
        verbose_name_plural = 'Настройки нормы часов'
        ordering = ['-year']
        unique_together = (
            ('year', 'sawh_settings'),
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
            raise ValidationError(_('Opens and closes fields are required for workday type'))

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


class ApiLog(AbstractModel):
    """
    Лог api.
    Необходим для того,
     чтобы пользователи системы (поддержка, админы, разработчики и т.д.)
     могли посмотреть лог получения данных по интеграции.

    Настраивается с помощью добавления настроек в Network.settings_values, например:
    {
        ...
        "api_log_settings": {
            "delete_gap": 60,  # можно переопределить сколько дней хранить лог (по умолчанию 90 в API_LOG_DELETE_GAP)
            "log_funcs": {
                "Employment": {  # функция, которую надо логировать (то же самое что в FunctionGroup.FUNCS_TUPLE)
                    "by_code": true,  # логируются только запросы по интеграции
                    "http_methods": ['POST'],  # какие http методы логировать
                    "save_response_codes": [400],  # сохранять ответ при опред. кодах. Полезно для дебага.
                }
            }
        }
        ...
    }
    """
    user = models.ForeignKey('base.User', on_delete=models.CASCADE)
    view_func = models.CharField(max_length=256)
    http_method = models.CharField(max_length=32)
    url_kwargs = models.TextField(blank=True)
    request_datetime = models.DateTimeField(auto_now_add=True)
    query_params = models.TextField(blank=True)
    request_path = models.CharField(max_length=128)
    request_data = models.TextField(blank=True)
    response_ms = models.PositiveIntegerField()
    response_datetime = models.DateTimeField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error_traceback = models.TextField(blank=True)

    class Meta:
        index_together = (
            ('view_func', 'http_method'),
        )

    @classmethod
    def clean_log(cls, network_id, delete_gap):
        cls.objects.filter(
            user__network_id=network_id,
            request_datetime__lte=timezone.now() - datetime.timedelta(days=delete_gap),
        ).delete()


class ShiftSchedule(AbstractActiveNetworkSpecificCodeNamedModel):
    employee = models.ForeignKey('base.Employee', null=True, blank=True, on_delete=models.CASCADE)

    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        unique_together = (
            ('code', 'network'),
            ('employee', 'network'),
        )
        verbose_name = 'График смен'
        verbose_name_plural = 'Графики смен'

    def __str__(self):
        s = f'{self.name}'
        if self.code:
            s += f' ({self.code})'
        return s

    @classmethod
    def _get_rel_objs_mapping(cls):
        return {
            'days': (ShiftScheduleDay, 'shift_schedule_id'),
        }


class ShiftScheduleDay(AbstractModel):
    code = models.CharField(max_length=256, null=True, blank=True, db_index=True)
    shift_schedule = models.ForeignKey(
        'base.ShiftSchedule', verbose_name='График смен', on_delete=models.CASCADE, related_name='days')
    dt = models.DateField()
    day_type = models.ForeignKey('timetable.WorkerDayType', on_delete=models.PROTECT, verbose_name='Тип дня')
    work_hours = models.DecimalField(
        decimal_places=2, max_digits=4, verbose_name='Сумма всех рабочих часов', default=Decimal("0.00"))
    day_hours = models.DecimalField(
        decimal_places=2, max_digits=4, verbose_name='Сумма дневных часов', default=Decimal("0.00"))
    night_hours = models.DecimalField(
        decimal_places=2, max_digits=4, verbose_name='Сумма ночных часов', default=Decimal("0.00"))

    class Meta(AbstractModel.Meta):
        verbose_name = 'День графика смен'
        verbose_name_plural = 'Дни графика смен'
        unique_together = (
            ('dt', 'shift_schedule'),
        )

    def __str__(self):
        s = f'{self.dt}'
        if self.code:
            s += f' ({self.code})'
        return s

    def clean(self):
        if (self.day_hours + self.night_hours) != self.work_hours:
            raise DjangoValidationError(_('Work hours should be sum of day hours and night hours'))


class ShiftScheduleInterval(AbstractModel):
    code = models.CharField(max_length=256, null=True, blank=True, db_index=True)
    shift_schedule = models.ForeignKey('base.ShiftSchedule', verbose_name='График смен', on_delete=models.PROTECT, related_name='intervals')
    employee = models.ForeignKey(
        'base.Employee', verbose_name='Сотрудник', on_delete=models.CASCADE, null=True, blank=True)
    dt_start = models.DateField(verbose_name='Дата с (включительно)')
    dt_end = models.DateField(verbose_name='Дата по (включительно)')

    class Meta(AbstractModel.Meta):
        verbose_name = 'Интервал графика смен сотрудника'
        verbose_name_plural = 'Интервалы графика смен сотрудника'
        # TODO: ограничение на невозможность создать для 1 сотрудника пересечения графика по датам ?

    def __str__(self):
        s = f'{self.shift_schedule} {self.employee} {self.dt_start}-{self.dt_end}'
        if self.code:
            s += f' ({self.code})'
        return s


class ContentBlock(AbstractActiveNetworkSpecificCodeNamedModel):
    name = models.CharField(max_length=128, verbose_name='Имя текстового блока')
    body = models.TextField(verbose_name='Тело блока (может передаваться контекст как в шаблонах django)')

    def get_body(self, request=None):
        context = {
            'request': request,
        }
        return Template(self.body).render(Context(context))
