from django.db import models
from django_celery_beat.models import CrontabSchedule


class ReportConfig(models.Model):
    cron = models.ForeignKey(
        CrontabSchedule,
        verbose_name='Расписание для отправки', on_delete=models.PROTECT,
    )
    shops = models.ManyToManyField(
        'base.Shop', blank=True, verbose_name='Фильтровать по выбранным отделам',
    )
    name = models.CharField(max_length=128)

    def __str__(self):
        return self.name
