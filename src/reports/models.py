from datetime import date, datetime
from pytz import timezone

from django.db.models import Q
from src.base.models import Employment, User
from src.reports.registry import ReportRegistryHolder
from src.base.models_abstract import AbstractActiveNetworkSpecificCodeNamedModel
from dateutil.relativedelta import relativedelta
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule


class ReportType(AbstractActiveNetworkSpecificCodeNamedModel):
    code = models.CharField(max_length=64, verbose_name='Код')

    class Meta:
        verbose_name = 'Тип отчета'
        verbose_name_plural = 'Типы отчетов'
        unique_together = (
            ('code', 'network'),
        )

    def __str__(self):
        return f'{self.name} ({self.code}) {self.network}'


class ReportConfig(models.Model):
    ACC_PERIOD_DAY = 'D'
    ACC_PERIOD_MONTH = 'M'
    ACC_PERIOD_QUARTER = 'Q'
    ACC_PERIOD_HALF_YEAR = 'H'
    ACC_PERIOD_YEAR = 'Y'

    PERIOD_START_TODAY = 'T'
    PERIOD_START_YESTERDAY = 'E'
    PERIOD_START_PREVIOUS_MONTH = 'M'
    PERIOD_START_PREVIOUS_QUARTER = 'Q'
    PERIOD_START_PREVIOUS_HALF_YEAR = 'H'
    PERIOD_START_PREVIOUS_YEAR = 'Y'

    ACCOUNTING_PERIOD_LENGTH_CHOICES = (
        (ACC_PERIOD_DAY, _('Day')),
        (ACC_PERIOD_MONTH, _('Month')),
        (ACC_PERIOD_QUARTER, _('Quarter')),
        (ACC_PERIOD_HALF_YEAR, _('Half a year')),
        (ACC_PERIOD_YEAR, _('Year')),
    )

    PERIOD_START_CHOICES = (
        (PERIOD_START_TODAY, _('Today')),
        (PERIOD_START_YESTERDAY, _('Yesterday')),
        (PERIOD_START_PREVIOUS_MONTH, _('End of previous month')),
        (PERIOD_START_PREVIOUS_QUARTER, _('End of previous quarter')),
        (PERIOD_START_PREVIOUS_HALF_YEAR, _('End of previous half a year')),
        (PERIOD_START_PREVIOUS_YEAR, _('End of previous year')),
    )
    report_type = models.ForeignKey('reports.ReportType', verbose_name='Тип отчета', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True, verbose_name='Активен')
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
    period_start = models.CharField(max_length=1, choices=PERIOD_START_CHOICES, 
        default=PERIOD_START_YESTERDAY, verbose_name='Начало периода')
    send_by_group_employments_shops = models.BooleanField(default=False, verbose_name='Фильтровать рассылку по магазинам трудоустройств групп')

    users = models.ManyToManyField('base.User', blank=True, verbose_name='Оповещать конкретных пользователей')
    groups = models.ManyToManyField(
        'base.Group', blank=True,
        verbose_name='Оповещать пользователей определенных групп',
        related_name='+',
    )
    email_addresses = models.CharField(
        max_length=256, null=True, blank=True, verbose_name='E-mail адреса получателей, через запятую')
    shops_to_notify = models.ManyToManyField(
        'base.Shop', blank=True, verbose_name='Оповещать по почте магазина', related_name='+',
    )

    email_text = models.TextField(
        verbose_name='E-mail текст',
        null=True, blank=True,
    )
    subject = models.CharField(
        max_length=256, verbose_name='Тема письма',
    )

    def __str__(self):
        return f'{self.name}, {self.report_type}'

    def get_dates(self, tz='UTC'):
        delta_mapping = {
            self.ACC_PERIOD_DAY: relativedelta(days=1),
            self.ACC_PERIOD_MONTH: relativedelta(months=1),
            self.ACC_PERIOD_QUARTER: relativedelta(months=3),
            self.ACC_PERIOD_HALF_YEAR: relativedelta(months=6),
            self.ACC_PERIOD_YEAR: relativedelta(years=1),
        }
        dt_to = self._get_start_date(datetime.now(tz=timezone(tz)).date())
        count = self.count_of_periods - 1 if self.period == self.ACC_PERIOD_DAY else self.count_of_periods
        dt_from = dt_to - (delta_mapping[self.period] * count)

        return {'dt_from': dt_from, 'dt_to': dt_to}

    def _get_start_date(self, dt):
        date_getters = {
            self.PERIOD_START_TODAY: lambda dt: dt,
            self.PERIOD_START_YESTERDAY: lambda dt: dt - relativedelta(days=1),
            self.PERIOD_START_PREVIOUS_MONTH: lambda dt: (dt - relativedelta(months=1)) + relativedelta(day=31),
            self.PERIOD_START_PREVIOUS_QUARTER: lambda dt: date(dt.year if dt.month > 3 else dt.year - 1, 3 * (((dt.month - 1) // 3) or 4), 1) + relativedelta(day=31),
            self.PERIOD_START_PREVIOUS_HALF_YEAR: lambda dt: date(dt.year if dt.month > 6 else dt.year - 1, 12 if dt.month <= 6 else 6, 1) + relativedelta(day=31),
            self.PERIOD_START_PREVIOUS_YEAR: lambda dt: date(dt.year - 1, 12, 31),
        }

        return date_getters[self.period_start](dt)

    def get_acc_period(self):
        acc_period_mapping = {
            self.ACC_PERIOD_MONTH: 1,
            self.ACC_PERIOD_QUARTER: 3,
            self.ACC_PERIOD_HALF_YEAR: 6,
            self.ACC_PERIOD_YEAR: 12,
        }
        return acc_period_mapping.get(self.period, 1)

    def get_file(self, context: dict):
        report_cls = ReportRegistryHolder.get_registry().get(self.report_type.code)
        if report_cls:
            return report_cls(
                network_id=self.report_type.network_id,
                context=context,
            ).get_file()
        else:
            return None


    def get_recipients(self):
        """
        :param context:
        :return: Список почт
        """
        recipients = []

        recipients.extend(list(self.users.filter(email__isnull=False).values_list('email', flat=True)))

        groups = list(self.groups.all())
        if groups and not self.send_by_group_employments_shops:
            recipients.extend(
                list(User.objects.filter(
                    id__in=Employment.objects.get_active().filter(
                        Q(function_group__in=groups) | Q(position__group__in=groups),
                    ).values_list('employee__user_id', flat=True),
                    email__isnull=False,
                ).values_list('email', flat=True))
            )

        shops = list(self.shops_to_notify.filter(email__isnull=False).values_list('email', flat=True))
        if shops:
            recipients.extend(
                shops
            )
    
        return recipients

    def __str__(self):
        return '{}, {} получателей{}'.format(
            self.report_type.name,
            self.shops_to_notify.count() + self.users.count()\
            + (len(self.email_addresses.split(',')) if self.email_addresses else 0),
            f', расписание {self.cron}',
        )
