from django.db import models


class CameraCashbox(models.Model):
    class Meta(object):
        verbose_name = 'Камеры-кассы'

    name = models.CharField(max_length=64)
    cashbox = models.ForeignKey('Cashbox', on_delete=models.PROTECT, null=True, blank=True)

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
    work_type = models.ForeignKey('WorkType', on_delete=models.PROTECT)


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

