from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule


class ReportConfig(models.Model):
    ACC_PERIOD_DAY = 'D'
    ACC_PERIOD_MONTH = 'M'
    ACC_PERIOD_QUARTER = 'Q'
    ACC_PERIOD_HALF_YEAR = 'H'
    ACC_PERIOD_YEAR = 'Y'

    ACCOUNTING_PERIOD_LENGTH_CHOICES = (
        (ACC_PERIOD_DAY, _('Day')),
        (ACC_PERIOD_MONTH, _('Month')),
        (ACC_PERIOD_QUARTER, _('Quarter')),
        (ACC_PERIOD_HALF_YEAR, _('Half a year')),
        (ACC_PERIOD_YEAR, _('Year')),
    )
    cron = models.ForeignKey(
        CrontabSchedule,
        verbose_name='Расписание для отправки', on_delete=models.PROTECT,
    )
    shops = models.ManyToManyField(
        'base.Shop', blank=True, verbose_name='Фильтровать по выбранным отделам',
    )
    name = models.CharField(max_length=128)

    count_of_periods = models.IntegerField(default=1, verbose_name='Количество периодов')
    period = models.CharField(max_length=1, choices=ACCOUNTING_PERIOD_LENGTH_CHOICES, 
        default=ACC_PERIOD_DAY, verbose_name='Период')
    include_today = models.BooleanField(default=False, verbose_name='Включать сегодняшний день')

    def __str__(self):
        return self.name

    def get_dates(self):
        delta_mapping = {
            self.ACC_PERIOD_DAY: relativedelta(days=1),
            self.ACC_PERIOD_MONTH: relativedelta(months=1),
            self.ACC_PERIOD_QUARTER: relativedelta(months=3),
            self.ACC_PERIOD_HALF_YEAR: relativedelta(months=6),
            self.ACC_PERIOD_YEAR: relativedelta(years=1),
        }
        dt_to = date.today()
        if not self.include_today:
            dt_to = dt_to - relativedelta(days=1)
        count = self.count_of_periods - 1 if self.period == self.ACC_PERIOD_DAY else self.count_of_periods
        dt_from = dt_to - (delta_mapping[self.period] * count)

        return {'dt_from': dt_from, 'dt_to': dt_to}
