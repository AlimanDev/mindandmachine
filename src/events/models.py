from django.contrib.postgres.fields import JSONField
from django.db import models

from src.base.models_abstract import AbstractModel, AbstractNamedModel


class EventType(AbstractNamedModel):
    code = models.CharField(max_length=64, unique=True, verbose_name='Код')
    write_history = models.BooleanField(default=True, verbose_name='Сохранять историю события')

    class Meta:
        verbose_name = 'Тип события'
        verbose_name_plural = 'Типы событий'

    def __str__(self):
        return f'{self.name} ({self.code})'


class EventHistory(AbstractModel):
    network = models.ForeignKey('base.Network', null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.ForeignKey('events.EventType', on_delete=models.CASCADE)
    user_author = models.ForeignKey('base.User', null=True, blank=True, on_delete=models.SET_NULL)
    shop = models.ForeignKey('base.Shop', null=True, blank=True, on_delete=models.SET_NULL)
    context = JSONField(default=dict)

    class Meta:
        verbose_name = 'История события'
        verbose_name_plural = 'История событий'
