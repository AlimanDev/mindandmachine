from dateutil.relativedelta import relativedelta
from django.db import models
from django.db.models.aggregates import Max, Min
from django.utils.functional import cached_property
import json

from src.base import models_utils
import datetime
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
    FORECAST_CHOICES = (
        (FORECAST, 'Forecast',),
        (FORECAST_FORMULA, 'Formula'),
    )

    is_special = models.BooleanField(default=False)
    work_type_name = models.OneToOneField('timetable.WorkTypeName', on_delete=models.PROTECT, null=True, blank=True, related_name='operation_type_name')
    do_forecast = models.CharField(max_length=1, default=FORECAST, choices=FORECAST_CHOICES)

    def __str__(self):
        return 'id: {}, name: {}, code: {}'.format(
            self.id,
            self.name,
            self.code,
        )


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
    forecast_step = models.DurationField(default=datetime.timedelta(hours=1))
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
    type = models.CharField(max_length=1, default=TYPE_FORMULA)
    max_value = models.FloatField(null=True, blank=True)
    threshold = models.FloatField(null=True, blank=True)
    days_of_week = models.CharField(max_length=48, null=True, blank=True, default='[0, 1, 2, 3, 4, 5, 6]')

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
        data = self.days_of_week
        if isinstance(data, str):
            data = json.loads(data or '[]')
        return data or []

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
                if tm_end == datetime.time(0):
                    tm_end = datetime.time(23, 59)
                if tm_start < tm_end:
                    filt |= (models.Q(dttm_forecast__week_day=week_day) & (models.Q(dttm_forecast__time__gte=tm_start) & models.Q(dttm_forecast__time__lt=tm_end)))
                elif tm_start > tm_end:
                    filt |= (models.Q(dttm_forecast__week_day=week_day) & (models.Q(dttm_forecast__time__gte=tm_start) | models.Q(dttm_forecast__time__lt=tm_end)))
            return self.filter(filt, *args, **kwargs)
        else:
            if not dt_from:
                dt_from = datetime.date.today().replace(day=1)
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
            max_shop_time = datetime.time(23, 59) if datetime.time(0,0) == shop_times['close'] else shop_times['close']
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
