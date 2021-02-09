from django.template import Template, Context

from src.base.models import Shop
from src.celery.celery import app
from .helpers import send_mass_html_mail, textify
from .models import (
    EventEmailNotification,
    EventOnlineNotification,
    EventWebhookNotification,
)


def enrich_context(context):
    if 'shop_id' in context:
        context['shop'] = Shop.objects.filter(id=context['shop_id']).first()


@app.task
def send_event_email_notifications(event_email_notification_id: int, user_author_id: int, context: dict):
    event_email_notification = EventEmailNotification.objects.select_related(
        'event_type',
    ).get(
        id=event_email_notification_id,
    )
    template = event_email_notification.get_email_template()
    enrich_context(context)
    subject = Template(event_email_notification.get_subject_template()).render(Context(context))
    attach_file = event_email_notification.get_file(user_author_id, context)
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
                    attach_file,
                    None,
                    [email]
                )
            )

    if event_email_notification.email_addresses:
        emails = event_email_notification.email_addresses.split(',')
        for email in emails:
            message_content = template.render(Context(context))
            datatuple.append(
                (
                    subject,
                    textify(message_content),
                    message_content,
                    attach_file,
                    None,
                    [email]
                )
            )

    send_mass_html_mail(datatuple=datatuple)


@app.task
def send_online_notifications(online_notification_id, user_author_id, context):
    pass


@app.task
def send_webhook_notifications(webhook_notification_id, user_author_id, context):
    pass


@app.task
def send_notifications_task(**kwargs):
    event_email_notifications = EventEmailNotification.objects.filter(
        event_type__code=kwargs.get('event_code'),
        event_type__network_id=kwargs.get('network_id'),
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
    )
    for webhook_notification in webhook_notifications:
        send_webhook_notifications.delay(
            webhook_notification_id=webhook_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )
