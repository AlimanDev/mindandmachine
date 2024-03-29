from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.template import loader as template_loader, Template
from django.utils.translation import gettext_lazy as _

from src.apps.base.models import User, Employment, Shop
from src.apps.base.models_abstract import AbstractModel
from src.apps.events.registry import EventRegistryHolder
from src.apps.notifications.templates import SYSTEM_EMAIL_TEMPLATES
from uuid import uuid4


class AbstractEventNotification(AbstractModel):
    event_type = models.ForeignKey('events.EventType', verbose_name='Тип события', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    class Meta:
        abstract = True
    
    def __str__(self):
        return self.event_type.name


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

    shop_parent = models.BooleanField(
        default=False, verbose_name=_('Parent shop')
    )
    shop_ancestors = models.BooleanField(
        default=False, verbose_name='Искать получателей среди пользователей магазинов предков')
    shop_descendants = models.BooleanField(
        default=False, verbose_name='Искать получателей среди пользователей магазинов потомков')
    shop_groups = models.ManyToManyField(
        'base.Group', blank=True, verbose_name='Оповещать пользователей магазина, имеющих выбранные группы',
        related_name='+',
    )
    employee_shop_groups = models.ManyToManyField(
        'base.Group', blank=True, verbose_name='Оповещать пользователей магазина сотрудника, имеющих выбранные группы',
        related_name='+',
    )
    shops = models.ManyToManyField(
        'base.Shop', blank=True, verbose_name='Оповещать по почте магазина',
    )

    class Meta:
        abstract = True

    def __str__(self):
        return '{}, {} получателей'.format(
            self.event_type.name,
            self.shops.count() + self.users.count(),
        )

    def get_recipients(self, user_author_id: int, context: dict):
        """
        :param user_author_id:
        :param context:
        :return: Список пользователей, которые должны получить оповещение
        """
        recipients = []
        network_filter = Q()
        if context.get('networks', []):
            network_filter = Q(network_id__in=context.get('networks', []))
        if self.get_recipients_from_event_type:
            event_cls = EventRegistryHolder.get_registry().get(self.event_type.code)
            if event_cls:
                event = event_cls(
                    network_id=self.event_type.network_id,
                    user_author_id=user_author_id,
                    context=context,
                )
                recipients.extend(list(event.get_recipients()))

        recipients.extend(list(self.users.filter(network_filter)))

        groups = list(self.groups.filter(network_filter))
        if groups:
            recipients.extend(
                list(User.objects.filter(
                    id__in=Employment.objects.get_active().filter(
                        Q(function_group__in=groups) | Q(position__group__in=groups),
                    ).values_list('employee__user_id', flat=True),
                    email__isnull=False,
                ))
            )

        shop_id = context.get('shop_id')
        if shop_id:
            shop = Shop.objects.get(id=shop_id)
            shop_q = Q(shop=shop)
            if self.shop_parent:
                shop_q |= Q(shop=shop.parent)
            elif self.shop_ancestors:
                shop_q |= Q(shop__in=shop.get_ancestors())
            if self.shop_descendants:
                shop_q |= Q(shop__in=shop.get_descendants())
            recipients.extend(
                list(User.objects.filter(
                    id__in=Employment.objects.get_active().filter(
                        Q(function_group__in=self.shop_groups.all()) | Q(position__group__in=self.shop_groups.all()),
                        shop_q,
                    ).values_list('employee__user_id', flat=True),
                    email__isnull=False,
                ))
            )
        
        employment_shop_id = context.get('employment_shop_id')
        if employment_shop_id:
            shop = Shop.objects.get(id=employment_shop_id)
            shop_q = Q(shop=shop)
            if self.shop_descendants:
                shop_q |= Q(shop__in=shop.get_descendants())
            if self.shop_ancestors:
                shop_q |= Q(shop__in=shop.get_ancestors())
            recipients.extend(
                list(User.objects.filter(
                    id__in=Employment.objects.get_active().filter(
                        Q(function_group__in=self.employee_shop_groups.all()) | Q(position__group__in=self.employee_shop_groups.all()),
                        shop_q,
                    ).values_list('employee__user_id', flat=True),
                    email__isnull=False,
                ))
            )

        employment_shop_ids = context.get('employment_shop_ids')
        if employment_shop_ids:
            shops = Shop.objects.filter(id__in=employment_shop_ids)
            shop_q = Q(shop__in=shops)
            if self.shop_descendants:
                for shop in shops:
                    shop_q |= Q(shop__in=shop.get_descendants())
            if self.shop_ancestors:
                for shop in shops:
                    shop_q |= Q(shop__in=shop.get_ancestors())
            list(User.objects.filter(
                id__in=Employment.objects.get_active().filter(
                    Q(function_group__in=self.employee_shop_groups.all()) | Q(position__group__in=self.employee_shop_groups.all()),
                    shop_q,
                ).values_list('employee__user_id', flat=True),
                email__isnull=False,
            ))

        shops = list(self.shops.filter(network_filter))
        if shops:
            recipients.extend(
                [
                    User(
                        pk=uuid4(),
                        email=s.email,
                    )
                    for s in shops
                ]
            )
    
        return recipients


class EventEmailNotification(AbstractEventNotificationWithRecipients):
    email_addresses = models.CharField(
        max_length=256, null=True, blank=True, verbose_name='E-mail адреса получателей, через запятую')
    system_email_template = models.CharField(
        max_length=256, choices=SYSTEM_EMAIL_TEMPLATES, verbose_name='Системный E-mail шаблон', null=True, blank=True)
    custom_email_template = models.TextField(
        verbose_name='Пользовательский E-mail шаблон',
        help_text='Будет использован только если не выбран "Системный E-mail шаблон"',
        null=True, blank=True,
    )
    subject = models.CharField(
        max_length=256, verbose_name='Тема письма', null=True, blank=True,
        help_text='По умолчанию берется из названия "Системный E-mail шаблон"'
    )

    class Meta:
        verbose_name = 'Email оповещение о событиях'
        verbose_name_plural = 'Email оповещения о событиях'

    def __str__(self):
        return '{} получателей{}'.format(
            self.event_type.name,
            self.shops.count() + self.users.count()\
            + (len(self.email_addresses.split(',')) if self.email_addresses else 0),
        )

    def clean(self):
        if not (self.system_email_template or self.custom_email_template):
            raise ValidationError(
                'Необходимо выбрать "Системный E-mail шаблон", либо заполнить "Пользовательский E-mail шаблон"'
            )

    def get_email_template(self):
        if self.system_email_template:
            return template_loader.get_template(self.system_email_template).template

        elif self.custom_email_template:
            return Template(self.custom_email_template)

    def get_subject_template(self):
        subject = ''
        if self.subject:
            subject = self.subject

        if not subject and self.system_email_template:
            subject = self.get_system_email_template_display()

        return subject


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
