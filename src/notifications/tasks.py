from django.conf import settings
from django.template import Template, Context

from src.base.models import Shop, User, Employee
from src.celery.celery import app
from .helpers import send_mass_html_mail, textify
from .models import (
    AbstractEventNotification,
    EventEmailNotification,
    EventOnlineNotification,
    EventWebhookNotification,
)


def enrich_context(context:dict, user_id: int, event: AbstractEventNotification):
    if 'shop_id' in context:
        context['shop'] = Shop.objects.filter(id=context['shop_id']).first()
    if 'employee_ids' in context:
        context['employees'] = Employee.objects.filter(id__in=context['employee_ids']).prefetch_related('user')
    context['host'] = settings.EXTERNAL_HOST
    context['author'] = User.objects.filter(id=user_id).first()
    context['shop_name_form'] = event.event_type.network.settings_values_prop.get('shop_name_form', {})
    context['DATE_FORMAT'] = settings.TEMPLATE_DATE_FORMAT
    context['TIME_FORMAT'] = settings.TEMPLATE_TIME_FORMAT


@app.task(time_limit=settings.EMAIL_TASK_TIMEOUT, serializer='yaml') # YAML correctly serializes datetimes
def send_event_email_notifications(event_email_notification_id: int, user_author_id: int, context: dict):
    event_email_notification = EventEmailNotification.objects.select_related(
        'event_type',
        'event_type__network',
    ).get(
        id=event_email_notification_id,
    )
    template = event_email_notification.get_email_template()
    enrich_context(context, user_author_id, event_email_notification)
    subject = Template(event_email_notification.get_subject_template()).render(Context(context))
    datatuple = []

    for recipient in set(event_email_notification.get_recipients(user_author_id, context)):
        # не шлем автору события (TODO: может быть сделать отдельный флаг в модели настроек?)
        if recipient.id == user_author_id:
            continue

        email = recipient.email
        if email:
            context_copy = context.copy()
            context_copy['recipient'] = recipient
            message_content = template.render(Context(context_copy))
            datatuple.append(
                (
                    subject,
                    textify(message_content),
                    message_content,
                    None,
                    None,
                    [email]
                )
            )

    if event_email_notification.email_addresses:
        emails = event_email_notification.email_addresses.split(',')
        message_content = template.render(Context(context))
        message_text = textify(message_content)
        for email in emails:
            datatuple.append(
                (
                    subject,
                    message_text,
                    message_content,
                    None,
                    None,
                    [email]
                )
            )

    return send_mass_html_mail(datatuple=datatuple)


@app.task(serializer='yaml')
def send_online_notifications(online_notification_id, user_author_id, context):
    pass


@app.task(serializer='yaml')
def send_webhook_notifications(webhook_notification_id, user_author_id, context):
    pass


@app.task(serializer='yaml')
def send_notifications_task(**kwargs):
    event_email_notifications = EventEmailNotification.objects.filter(
        event_type__code=kwargs.get('event_code'),
        event_type__network_id=kwargs.get('network_id'),
        is_active=True,
    )

    for event_email_notification in event_email_notifications:
        send_event_email_notifications.delay(
            event_email_notification_id=event_email_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )

    online_notifications = EventOnlineNotification.objects.filter(
        event_type__code=kwargs.get('event_code'),
        event_type__network_id=kwargs.get('network_id'),
        is_active=True,
    )
    for online_notification in online_notifications:
        send_online_notifications.delay(
            online_notification_id=online_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )

    webhook_notifications = EventWebhookNotification.objects.filter(
        event_type__code=kwargs.get('event_code'),
        event_type__network_id=kwargs.get('network_id'),
        is_active=True,
    )
    for webhook_notification in webhook_notifications:
        send_webhook_notifications.delay(
            webhook_notification_id=webhook_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )
