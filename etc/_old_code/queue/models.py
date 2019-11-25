from django.db import models


class PeriodProducts(PeriodDemand):
    class Meta(object):
        verbose_name = 'Спрос по продуктам'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    value = models.FloatField(default=0)


class PeriodQueues(PeriodDemand):
    class Meta(object):
        verbose_name = 'Очереди'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.dttm_forecast, self.type, self.operation_type, self.value)

    value = models.FloatField(default=0)
