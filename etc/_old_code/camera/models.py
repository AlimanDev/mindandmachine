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

