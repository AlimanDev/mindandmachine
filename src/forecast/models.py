import re
from dateutil.relativedelta import relativedelta
from django.db import models, transaction
from django.db.models.aggregates import Max, Min
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from rest_framework import serializers
import json

from src.base import models_utils
from datetime import timedelta, date, datetime, time
from django.utils import timezone

from src.base.models_abstract import AbstractModel, AbstractActiveModel, AbstractActiveNetworkSpecificCodeNamedModel
from src.base.models import Shop, ShopSchedule

from src.timetable.models import WorkType, WorkTypeName, Network


class OperationTypeName(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Название операции'
        verbose_name_plural = 'Названия операций'

    def delete(self):
        super(OperationTypeName, self).delete()
        OperationType.objects.filter(operation_type_name__id=self.pk).update(
            dttm_deleted=timezone.now()
        )
        return self

    FORECAST = 'H'
    FORECAST_FORMULA = 'F'
    FEATURE_SERIE = 'FS'
    FORECAST_CHOICES = (
        (FORECAST, 'Forecast',),
        (FORECAST_FORMULA, 'Formula'),
        (FEATURE_SERIE, 'Feature serie'),
    )

    is_special = models.BooleanField(default=False)
    work_type_name = models.OneToOneField('timetable.WorkTypeName', on_delete=models.PROTECT, null=True, blank=True, related_name='operation_type_name')
    do_forecast = models.CharField(max_length=2, default=FORECAST, choices=FORECAST_CHOICES)

    def __str__(self):
        return 'id: {}, name: {}, code: {}'.format(
            self.id,
            self.name,
            self.code,
        )

    def save(self, *args, **kwargs):
        if self.work_type_name_id:
            self.do_forecast = self.FORECAST_FORMULA
        return super().save(*args, **kwargs)


class LoadTemplate(AbstractModel):
    class Meta:
        verbose_name = 'Шаблон нагрузки'
        verbose_name_plural = 'Шаблоны нагрузки'

    name = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=128, unique=True, null=True, blank=True)
    network = models.ForeignKey(Network, on_delete=models.PROTECT, null=True)
    forecast_params = models.TextField(default='{}')
    round_delta = models.FloatField(default=0)

    def __str__(self):
        return f'id: {self.id}, name: {self.name}'


class OperationType(AbstractActiveModel):
    class Meta:
        verbose_name = 'Тип операции'
        verbose_name_plural = 'Типы операций'
        unique_together = ['shop', 'operation_type_name']

    def __str__(self):
        return 'id: {}, name: {}, work type: {}'.format(self.id, self.operation_type_name.name, self.work_type)

    READY = 'R'
    UPDATED = 'U'

    STATUSES = [
        (READY, 'Применён'),
        (UPDATED, 'Обновлён'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, blank=True, null=True, related_name='operation_types')
    work_type = models.OneToOneField(WorkType, on_delete=models.PROTECT, related_name='operation_type', null=True, blank=True)
    operation_type_name = models.ForeignKey(OperationTypeName, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=1,
        default=UPDATED,
        choices=STATUSES,
    )

    period_demand_params = models.CharField(
        max_length=1024,
        default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 200, "reg_lambda": 2, "silent": 1, "iterations": 20}'
    )

    def __init__(self, *args, **kwargs):
        code = kwargs.pop('code', None)
        super(OperationType, self).__init__(*args, **kwargs)
        if code:
            self.operation_type_name = OperationTypeName.objects.get(code=code)

    def save(self, *args, **kwargs):
        if hasattr(self, 'code'):
            self.operation_type_name = OperationTypeName.objects.get(code=self.code)
        super(OperationType, self).save(*args, **kwargs)

    def get_department(self):
        return self.shop


class OperationTypeTemplate(AbstractModel):
    class Meta:
        verbose_name = 'Шаблон типа операции'
        verbose_name_plural = 'Шаблоны типов операций'
        unique_together = ('load_template', 'operation_type_name')

    load_template = models.ForeignKey(LoadTemplate, on_delete=models.CASCADE, related_name='operation_type_templates')
    operation_type_name = models.ForeignKey(OperationTypeName, on_delete=models.PROTECT)
    tm_from = models.TimeField(null=True, blank=True)
    tm_to = models.TimeField(null=True, blank=True)
    forecast_step = models.DurationField(default=timedelta(hours=1))
    const_value = models.FloatField(null=True, blank=True)

    def __str__(self):
        return 'id: {}, load_template: {}, operation_type_name: ({})'.format(
                 self.id,
                 self.load_template.name,
                 self.operation_type_name,
            )


class OperationTypeRelation(AbstractModel):
    class Meta:
        verbose_name = 'Отношение типов операций'
        verbose_name_plural = 'Отношения типов операций'
        unique_together = ('base', 'depended')

    TYPE_FORMULA = 'F'
    TYPE_PREDICTION = 'P'
    TYPE_CHANGE_WORKLOAD_BETWEEN = 'C'
    TYPES = [
        (TYPE_FORMULA, 'Формула'),
        (TYPE_PREDICTION, 'Прогнозирование'),
        (TYPE_CHANGE_WORKLOAD_BETWEEN, 'Перекидывание нагрузки между типами работ'),
    ]

    base = models.ForeignKey(OperationTypeTemplate, on_delete=models.CASCADE, related_name='depends') # child
    depended = models.ForeignKey(OperationTypeTemplate, on_delete=models.CASCADE, related_name='bases') # parent
    formula = models.CharField(max_length=1024, null=True, blank=True)
    type = models.CharField(max_length=1, default=TYPE_FORMULA, choices=TYPES)
    max_value = models.FloatField(null=True, blank=True)
    threshold = models.FloatField(null=True, blank=True)
    days_of_week = models.CharField(max_length=48, null=True, blank=True, default='[0, 1, 2, 3, 4, 5, 6]')
    order = models.IntegerField(null=True, blank=True)

    def __str__(self):
        text = 'base_id {}, depended_id: {},'.format(
            self.base_id,
            self.depended_id,
        )
        if self.formula:
            text += f' formula: {self.formula}'
        else:
            text += f' max_value: {self.max_value}, threshold: {self.threshold}, days_of_week: {self.days_of_week}'
        return text

    @cached_property
    def days_of_week_list(self):
        available_days_of_week = {0, 1, 2, 3, 4, 5, 6}
        data = self.days_of_week
        if isinstance(data, str):
            data = json.loads(data or '[]')
        return list(set(data).intersection(available_days_of_week))
    
    def _enrich_error_msg(self, msg):
        row = self.row
        if row:
            row = _('Error in row {}.').format(row) + ' '
        return (row or '') + msg

    def __init__(self, *args, **kwargs):
        self.row = kwargs.pop('row', None)
        super().__init__(*args, **kwargs)

    def get_relation_type(self):
        base = self.base
        depended = self.depended
        type = None

        is_base_work_type = bool(base.operation_type_name.work_type_name_id)
        is_depended_work_type = bool(depended.operation_type_name.work_type_name_id)

        types_coniditions = [
            (
                self.formula and base.operation_type_name.do_forecast == OperationTypeName.FORECAST_FORMULA and\
                depended.operation_type_name.do_forecast in [OperationTypeName.FORECAST_FORMULA, OperationTypeName.FORECAST] and\
                not is_depended_work_type,
                self.TYPE_FORMULA,
            ),
            (
                base.operation_type_name.do_forecast == OperationTypeName.FORECAST_FORMULA and (
                    is_base_work_type and is_depended_work_type
                ) and self.max_value and self.threshold and self.days_of_week,
                self.TYPE_CHANGE_WORKLOAD_BETWEEN,
            ),
            (
                base.operation_type_name.do_forecast == OperationTypeName.FORECAST and\
                depended.operation_type_name.do_forecast in [OperationTypeName.FORECAST, OperationTypeName.FEATURE_SERIE],
                self.TYPE_PREDICTION,
            )
        ]
        for condition, t in types_coniditions:
            if condition:
                type = t
                break
        
        if not type:
            change_workload_between_required_errors = [
                (self.max_value, _('max value')),
                (self.threshold, _('threshold')),
                (self.days_of_week, _('days of week')),
            ]
            check_conditions = [
                (
                    base.operation_type_name.do_forecast == OperationTypeName.FORECAST_FORMULA and\
                    depended.operation_type_name.do_forecast in [OperationTypeName.FORECAST_FORMULA, OperationTypeName.FORECAST] and\
                    not is_depended_work_type and not self.formula,
                    self._enrich_error_msg(_('Formula required in relation {} -> {}').format(base.operation_type_name.name, depended.operation_type_name.name)),
                ),
                (
                    base.operation_type_name.do_forecast == OperationTypeName.FORECAST_FORMULA and (
                        is_base_work_type and is_depended_work_type
                    ) and not (self.max_value and self.threshold and self.days_of_week),
                    self._enrich_error_msg(
                        _("For relation 'change workload between' {} are required.").format(
                            ', '.join([msg for cond, msg in change_workload_between_required_errors if not cond])
                        )
                    ),
                ),
                (
                    base.operation_type_name.do_forecast == OperationTypeName.FORECAST and\
                    depended.operation_type_name.do_forecast == OperationTypeName.FORECAST_FORMULA,
                    self._enrich_error_msg(_(
                            'Forecast type {} cannot be depended from {} with formula type.'
                        ).format(base.operation_type_name.name, depended.operation_type_name.name)
                    ),
                ),
                (
                    not is_base_work_type and is_depended_work_type,
                    self._enrich_error_msg(_('Operation type {} cannot be depended from work type {}.').format(base.operation_type_name.name, depended.operation_type_name.name)),
                ),
                (
                    base.operation_type_name.do_forecast != OperationTypeName.FORECAST and\
                    depended.operation_type_name.do_forecast == OperationTypeName.FEATURE_SERIE,
                    self._enrich_error_msg(_('Only forecast types can depend from feature serie.')),
                ),
                (
                    base.operation_type_name.do_forecast == OperationTypeName.FEATURE_SERIE,
                    self._enrich_error_msg(_('Feature serie {} cannot have dependences.').format(base.operation_type_name.name)),
                )
            ]
            for condition, error_msg in check_conditions:
                if condition:
                    raise serializers.ValidationError(error_msg)
        
        return type

    def _check_relations(self, base_id, depended_id):
        relations = self.relations.get(depended_id)
        if not relations:
            return
        else:
            for relation in relations:
                if relation == base_id:
                    raise serializers.ValidationError(self._enrich_error_msg(_("Demand model cannot depend on itself.")))
                else:
                    self._check_relations(base_id, relation)
    
    def check_reverse_relation(self):
        from src.forecast.load_template.utils import create_operation_type_relations_dict
        if OperationTypeRelation.objects.filter(base_id=self.depended_id, depended_id=self.base_id).exists():
            raise serializers.ValidationError(self._enrich_error_msg(_("Backward dependency already exists.")))
        self.relations = create_operation_type_relations_dict(self.base.load_template_id)

        self._check_relations(self.base_id, self.depended_id)

    def save(self, *args, **kwargs):
        if self.depended_id == self.base_id:
            raise serializers.ValidationError(self._enrich_error_msg(_("Base and depended demand models cannot be the same.")))

        if (self.depended.load_template_id != self.base.load_template_id):
            raise serializers.ValidationError(self._enrich_error_msg(_("Base and depended demand models cannot have different templates.")))

        if (self.depended.forecast_step == timedelta(hours=1) and not (self.base.forecast_step in [timedelta(hours=1), timedelta(minutes=30)])) or\
           (self.depended.forecast_step == timedelta(minutes=30) and not (self.base.forecast_step in [timedelta(minutes=30)])):
            raise serializers.ValidationError(
                self._enrich_error_msg(
                    _("Depended must have same or bigger forecast step, got {} -> {}").format(
                        self.depended.forecast_step, self.base.forecast_step,
                    )
                )
            )

        self.days_of_week = self.days_of_week_list
        self.type = self.get_relation_type()
        if self.type == self.TYPE_FORMULA:
            lambda_check = r'^(if|else|\+|-|\*|/|\s|a|[0-9]|=|>|<|\.|\(|\))*'
            if not re.fullmatch(lambda_check, self.formula):
                raise serializers.ValidationError(
                    self._enrich_error_msg(_("Error in formula: {formula}.").format(formula=self.formula))
                )
            self.max_value = None
            self.threshold = None
            self.order = None
            self.days_of_week = []
        elif self.type == self.TYPE_PREDICTION:
            self.formula = None
            self.max_value = None
            self.threshold = None
            self.order = None
            self.days_of_week = []
        elif self.type == self.TYPE_CHANGE_WORKLOAD_BETWEEN:
            if not self.order:
                self.order = 999
        
        with transaction.atomic():
            super().save(*args, **kwargs)
            if not self.type == self.TYPE_CHANGE_WORKLOAD_BETWEEN:
                self.check_reverse_relation()


class OperationTemplate(AbstractActiveNetworkSpecificCodeNamedModel):
    """
        Шаблоны операций.
        В соответствии с ними создаются записи в PeriodClients
        Пример 1:
        {
            name: Уборка
            operation_type_id: 1,
            tm_start: 10:00:00
            tm_end: 12:00:00
            period: W
            days_in_period: [1,3,5]
            value: 2.5
        }
        В PeriodClients создадутся записи о потребности в двух с половиной людях
            с 10 до 12 в пн, ср, пт каждую неделю

        Пример 2:
        {
            name: Уборка
            operation_type_id: 1,
            tm_start: 10:00:00
            tm_end: 12:00:00
            period: M
            days_in_period: [1,3,5,15]
            value: 1
        }
        В PeriodClients создадутся записи о потребности в 1 человеке
            с 10 до 12 каждый месяц 1,3,5,15 числа
    """
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Шаблон операций'
        verbose_name_plural = 'Шаблоны операций'

    def __str__(self):
        return 'id: {}, name: {}, period: {}, days_in_period: {}, operation type: {}'.format(
            self.id,
            self.name,
            self.period,
            self.days_in_period,
            self.operation_type.operation_type_name.name)

    PERIOD_DAILY = 'D'
    PERIOD_WEEKLY = 'W'
    PERIOD_MONTHLY = 'M'
    PERIOD_CHOICES = (
        (PERIOD_DAILY, 'Ежедневно',),
        (PERIOD_WEEKLY, 'В неделю',),
        (PERIOD_MONTHLY, 'В месяц',),
    )

    operation_type = models.ForeignKey(OperationType, on_delete=models.PROTECT, related_name='opeartion_templates')
    tm_start = models.TimeField()
    tm_end = models.TimeField()
    value = models.FloatField()
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=64, default='', blank=True)

    period = models.CharField(
        max_length=1,
        default=PERIOD_DAILY,
        choices=PERIOD_CHOICES,
    )

    # days_in_period = models.TextField()
    days_in_period = models_utils.IntegerListField()
    # день до которого заполнен PeriodClients
    dt_built_to = models.DateField(blank=True, null=True)

    def check_days_in_period(self):
        # days_in_period = json.loads(self.days_in_period)
        if self.period == self.PERIOD_WEEKLY:
            for d in self.days_in_period:
                if d < 1 or d > 7:
                    return False
        elif self.period == self.PERIOD_MONTHLY:
            for d in self.days_in_period:
                if d < 1 or d > 31:
                    return False
        return True

    def generate_dates(self, dt_from, dt_to):
        def generate_times(dt, step):
            dt0 = datetime.combine(dt, self.tm_start)
            dt1 = datetime.combine(dt, self.tm_end)
            while dt0 < dt1:
                yield dt0
                dt0 += timedelta(minutes=step)

        days_in_period = self.days_in_period
        shop = self.operation_type.work_type.shop
        step = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute

        if self.period == self.PERIOD_DAILY:
            while dt_from <= dt_to:
                for t in generate_times(dt_from, step):
                    yield t
                dt_from += timedelta(days=1)
            return

        lambda_get_day = None
        if self.period == self.PERIOD_WEEKLY:
            lambda_get_day = lambda dt: dt.isoweekday()
        elif self.period == self.PERIOD_MONTHLY:
            lambda_get_day = lambda dt: dt.day

        day = lambda_get_day(dt_from)
        while dt_from <= dt_to:
            for period_day in days_in_period:
                if period_day < day:
                    continue
                elif period_day > day:
                    delta = period_day - day
                    dt_from += timedelta(days=delta)
                    if dt_from > dt_to:
                        return

                for t in generate_times(dt_from, step):
                    yield t
                dt_from += timedelta(days=1)
                if dt_from > dt_to:
                    return
                day = lambda_get_day(dt_from)
            if day == days_in_period[0]:
                for t in generate_times(dt_from, step):
                    yield t

            dt_from += timedelta(days=1)
            day = lambda_get_day(dt_from)

    def get_department(self):
        return self.operation_type.work_type.shop


class PeriodClientsManager(models.Manager):
    def shop_times_filter(self, shop, *args, weekday=False, dt_from=None, dt_to=None, **kwargs):
        '''
        param:
        shop - Shop object
        dt_from - date object
        dt_to - date object
        weekday - bool - смотреть по дням недели
        https://docs.djangoproject.com/en/3.0/ref/models/querysets/#week-day
        '''
        if weekday and not shop.open_times.get('all', False):
            filt = models.Q()
            for k, v in shop.open_times.items():
                tm_start = v
                tm_end = shop.close_times[k]
                week_day = (int(k) + 2) % 7 or 7
                if tm_end == time(0):
                    tm_end = time(23, 59)
                if tm_start < tm_end:
                    filt |= (models.Q(dttm_forecast__week_day=week_day) & (models.Q(dttm_forecast__time__gte=tm_start) & models.Q(dttm_forecast__time__lt=tm_end)))
                elif tm_start > tm_end:
                    filt |= (models.Q(dttm_forecast__week_day=week_day) & (models.Q(dttm_forecast__time__gte=tm_start) | models.Q(dttm_forecast__time__lt=tm_end)))
            return self.filter(filt, *args, **kwargs)
        else:
            if not dt_from:
                dt_from = date.today().replace(day=1)
            if not dt_to:
                dt_to = dt_from + relativedelta(day=31)
            shop_times = ShopSchedule.objects.filter(
                shop_id=shop.id,
                dt__gte=dt_from,
                dt__lte=dt_to,
                type=ShopSchedule.WORKDAY_TYPE,
            ).aggregate(
                open=Min('opens'),
                close=Max('closes'),
            )
            max_shop_time = time(23, 59) if time(0,0) == shop_times['close'] else shop_times['close']
            min_shop_time = shop_times['open']
            time_filter = {}
            if max_shop_time != min_shop_time:
                time_filter['dttm_forecast__time__gte'] = min_shop_time if min_shop_time < max_shop_time else max_shop_time
                time_filter['dttm_forecast__time__lt'] = max_shop_time if min_shop_time < max_shop_time else min_shop_time
            kwargs.update(time_filter)
        return self.filter(*args, **kwargs)


class PeriodClients(AbstractModel):
    LONG_FORECASE_TYPE = 'L'
    SHORT_FORECAST_TYPE = 'S'
    FACT_TYPE = 'F'

    FORECAST_TYPES = (
        (LONG_FORECASE_TYPE, 'Long'),
        (SHORT_FORECAST_TYPE, 'Short'),
        (FACT_TYPE, 'Fact'),
    )

    class Meta(object):
        verbose_name = 'Значение операций'
        unique_together = [
            ('dttm_forecast', 'operation_type', 'type'),
        ]
    
    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    id = models.BigAutoField(primary_key=True)
    dttm_forecast = models.DateTimeField()
    type = models.CharField(choices=FORECAST_TYPES, max_length=1, default=LONG_FORECASE_TYPE)
    operation_type = models.ForeignKey(OperationType, on_delete=models.PROTECT)
    value = models.FloatField(default=0)
    objects = PeriodClientsManager()


class PeriodDemandChangeLog(AbstractModel):
    class Meta(object):
        verbose_name = 'Лог изменений спроса'

    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(
            self.operation_type.name,
            self.operation_type.work_type.shop.name,
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


class Receipt(AbstractModel):
    """
    Событийная сущность, которая потом используется для аггрегации в PeriodClients

    изначально для чеков
    """

    class Meta:
        verbose_name = 'Событийные данные'
        verbose_name_plural = 'Событийные данные'
        index_together = (
            ('dt', 'data_type', 'shop'),
        )

    # id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=256, db_index=True)
    dttm = models.DateTimeField(verbose_name='Дата и время события')
    dt = models.DateField(verbose_name='Дата события')
    dttm_added = models.DateTimeField(auto_now_add=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, blank=True, null=True)
    info = models.TextField()
    data_type = models.CharField(max_length=128, verbose_name='Тип данных', null=True, blank=True)
    version = models.IntegerField(verbose_name='Версия объекта', default=0)
