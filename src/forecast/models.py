from django.db import models

from src.base import models_utils
import datetime

from src.timetable.models import WorkType

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


class OperationTemplate(models.Model):
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
    class Meta:
        verbose_name = 'Шаблон операций'
        verbose_name_plural = 'Шаблоны операций'

    def __str__(self):
        return 'id: {}, name: {}, period: {}, days_in_period: {}, operation type: {}'.format(
            self.id,
            self.name,
            self.period,
            self.days_in_period,
            self.operation_type.name)

    PERIOD_DAILY = 'D'
    PERIOD_WEEKLY = 'W'
    PERIOD_MONTHLY = 'M'
    PERIOD_CHOICES = (
        (PERIOD_DAILY, 'Ежедневно',),
        (PERIOD_WEEKLY, 'В неделю',),
        (PERIOD_MONTHLY, 'В месяц',),
    )


    dttm_added = models.DateTimeField(auto_now_add=True)
    dttm_deleted = models.DateTimeField(blank=True, null=True)

    operation_type = models.ForeignKey(OperationType, on_delete=models.PROTECT, related_name='work_type_reversed')
    name = models.CharField(max_length=128)
    tm_start = models.TimeField()
    tm_end = models.TimeField()
    value = models.FloatField()

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
            dt0 = datetime.datetime.combine(dt, self.tm_start)
            dt1 = datetime.datetime.combine(dt, self.tm_end)
            while dt0 < dt1:
                yield dt0
                dt0 += datetime.timedelta(minutes=step)

        days_in_period = self.days_in_period
        shop = self.operation_type.work_type.shop
        step = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute

        if self.period == self.PERIOD_DAILY:
            while dt_from <= dt_to:
                for t in generate_times(dt_from, step):
                    yield t
                dt_from += datetime.timedelta(days=1)
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
                    dt_from += datetime.timedelta(days=delta)
                    if dt_from > dt_to:
                        return

                for t in generate_times(dt_from, step):
                    yield t
                dt_from += datetime.timedelta(days=1)
                if dt_from > dt_to:
                    return
                day = lambda_get_day(dt_from)
            if day == days_in_period[0]:
                for t in generate_times(dt_from, step):
                    yield t

            dt_from += datetime.timedelta(days=1)
            day = lambda_get_day(dt_from)


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
        verbose_name = 'Значение операций'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

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

