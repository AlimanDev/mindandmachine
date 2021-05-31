from src.base.models_abstract import AbstractActiveModel

from django.db import models
from django.db.models.query import QuerySet
from django.utils import timezone
from mptt.models import MPTTModel

from src.base.models_abstract import AbstractActiveModel
from src.base.models_abstract import (
    AbstractActiveModel,
    AbstractModel,
    AbstractActiveNetworkSpecificCodeNamedModel,
    NetworkSpecificModel,
    AbstractCodeNamedModel,
)


class TaskManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(dttm_deleted__date__gt=timezone.now().date()) | models.Q(dttm_deleted__isnull=True)
        )


class TaskQuerySet(QuerySet):
    def delete(self):
        self.update(dttm_deleted=timezone.now())


class Task(AbstractActiveModel):
    code = models.CharField(max_length=128, null=True, blank=True, unique=True)
    dt = models.DateField(
        verbose_name='Дата, к которой относится задача (для ночных смен)',
        help_text='По умолчанию берется из времени начала',
    )
    dttm_start_time = models.DateTimeField(verbose_name='Время начала')
    dttm_end_time = models.DateTimeField(verbose_name='Время окончания')
    operation_type = models.ForeignKey('forecast.OperationType', on_delete=models.CASCADE)
    employee = models.ForeignKey('base.Employee', on_delete=models.CASCADE, verbose_name='Сотрудник')
    dttm_event = models.DateTimeField(null=True, blank=True, verbose_name='Время события создания/изменения объекта')

    objects = TaskManager.from_queryset(TaskQuerySet)()
    objects_with_excluded = models.Manager.from_queryset(TaskQuerySet)()

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'

    def save(self, **kwargs):
        if self.dt is None:
            self.dt = self.dttm_start_time.date()
        return super().save(**kwargs)
