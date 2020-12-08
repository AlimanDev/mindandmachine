from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.template import loader as template_loader, Template

from src.base.models import User, Employment, Shop
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
    subject = models.CharField(max_length=256, verbose_name='Тема письма', null=True, blank=True)

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
        recipients.extend(list(self.groups.all()))
        shop_id = context.get('shop_id')
        if shop_id:
            shop = Shop.objects.get(id=shop_id)
            shop_q = Q(shop=shop)
            if self.shop_descendants:
                shop_q |= Q(shop__in=shop.get_descendants())
            if self.shop_ancestors:
                shop_q |= Q(shop__in=shop.get_ancestors())
            recipients.extend(
                list(User.objects.filter(
                    id__in=Employment.objects.get_active().filter(
                        Q(function_group__in=self.shop_groups.all()) | Q(position__group__in=self.shop_groups.all()),
                        shop_q,
                    ).values_list('user_id', flat=True),
                    email__isnull=False,
                ))
            )
        recipients.extend(
            list(User.objects.filter(
                id__in=Employment.objects.get_active().filter(
                    Q(function_group__in=self.groups.all()) | Q(position__group__in=self.groups.all()),
                ).values_list('user_id', flat=True),
                email__isnull=False,
            ))
        )
        emails = [r.email.strip() for r in recipients if r.email]
        if self.email_addresses:
            emails.extend(self.email_addresses.split(','))
        return list(set(emails))

    def get_email_template(self):
        if self.system_email_template:
            return template_loader.get_template(self.system_email_template)

        elif self.custom_email_template:
            return Template(self.custom_email_template)


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
