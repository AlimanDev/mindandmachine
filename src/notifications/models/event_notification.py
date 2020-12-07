from django.core.exceptions import ValidationError
from django.db import models

from src.base.models import User, Employment
from src.base.models_abstract import AbstractModel
from src.events.registry import EventRegistryHolder
from src.notifications.templates import SYSTEM_EMAIL_TEMPLATES


class AbstractEventNotification(AbstractModel):
    event_type = models.ForeignKey('events.EventType', verbose_name='Тип события', on_delete=models.CASCADE)

    class Meta:
        abstract = True


class AbstractEventNotificationWithRecipients(AbstractEventNotification):
    get_recipients_from_event_type = models.BooleanField(
        default=False, verbose_name='Получать пользователей из события',
        help_text='Использовать жесткий алгоритм определения получателей, '
                  'привязаный к событию и его контексту (работает только для захардкоженных событий)')
    users = models.ManyToManyField('base.User', blank=True, verbose_name='Оповещать конкретных пользователей')
    groups = models.ManyToManyField(
        'base.Group', blank=True,
        verbose_name='Оповещать пользователей определенных групп',
        related_name='+',
    )

    shop_ancestors = models.BooleanField(
        default=False, verbose_name='Искать получателей среди пользователей магазинов предков')
    shop_descendants = models.BooleanField(
        default=False, verbose_name='Искать получателей среди пользователей магазинов потомков')
    shop_groups = models.ManyToManyField(
        'base.Group', blank=True, verbose_name='Оповещать пользователей магазина, имеющих выбранные группы',
        related_name='+',
    )

    class Meta:
        abstract = True


class EventEmailNotification(AbstractEventNotificationWithRecipients):
    email_addresses = models.CharField(
        max_length=256, null=True, blank=True, verbose_name='E-mail адреса получателей, через запятую')
    smtp_server_settings = models.ForeignKey(
        'notifications.SmtpServerSettings', on_delete=models.CASCADE, verbose_name='Настройки smtp-сервера'
    )
    system_email_template = models.CharField(
        max_length=256, choices=SYSTEM_EMAIL_TEMPLATES, verbose_name='Системный E-mail шаблон', null=True, blank=True)
    custom_email_template = models.TextField(verbose_name='Пользовательский E-mail шаблон', null=True, blank=True)

    class Meta:
        verbose_name = 'Email оповещение о событиях'
        verbose_name_plural = 'Email оповещения о событиях'

    def clean(self):
        if self.system_email_template and self.custom_email_template:
            raise ValidationError(
                'Нужно оставить что-то одно: "Системный E-mail шаблон" или "Пользовательский E-mail шаблон"'
            )

        if not (self.system_email_template or self.custom_email_template):
            raise ValidationError(
                'Необходимо выбрать "Системный E-mail шаблон", либо заполнить "Пользовательский E-mail шаблон"'
            )

    def get_recipients(self, user_author_id, context):
        recipients = []
        if self.get_recipients_from_event_type:
            event_cls = EventRegistryHolder.get_registry().get(self.event_type.code)
            if event_cls:
                event = event_cls(
                    user_author_id=user_author_id,
                    context=context,
                )
                recipients.extend(list(event.get_recipients()))
        recipients.extend(list(self.users.all()))
        recipients.extend(
            list(User.objects.filter(
                id__in=self.groups.filter(
                    employment__in=Employment.objects.get_active()
                ).values_list('employment__user_id', flat=True),
                email__isnull=False,
            ))
        )
        recipients.extend(self.email_addresses.split(','))
        emails = list(set(r.email.strip() for r in recipients if r.email))
        return emails


class EventOnlineNotification(AbstractEventNotificationWithRecipients):
    class Meta:
        verbose_name = 'Онлайн оповещение о событие'
        verbose_name_plural = 'Онлайн оповещения о событиях'


class EventWebhookNotification(AbstractEventNotification):
    webhook_notification_settings = models.ForeignKey(
        'notifications.WebhookSettings',
        on_delete=models.CASCADE, verbose_name='Настройки webhook оповещений',
    )

    class Meta:
        verbose_name = 'Webhook оповещение о событиях'
        verbose_name_plural = 'Webhook оповещения о событиях'
