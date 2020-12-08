from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail import get_connection

from src.celery.celery import app
from .helpers import textify
from .models import (
    EventEmailNotification,
    EventOnlineNotification,
    EventWebhookNotification,
)


@app.task
def send_event_email_notifications(event_email_notification_id, user_author_id, context):
    event_email_notification = EventEmailNotification.objects.select_related(
        'event_type', 'smtp_server_settings',
    ).get(id=event_email_notification_id)
    connection = get_connection(
        backend=settings.EMAIL_BACKEND,
        **event_email_notification.smtp_server_settings.get_smtp_server_settings()
    )
    content = event_email_notification.get_email_template().render(context)
    msg = EmailMultiAlternatives(
        connection=connection,
        subject=event_email_notification.subject,
        body=textify(content),
        to=event_email_notification.get_recipients(user_author_id, context),
        alternatives=[
            (content, 'text/html'),
        ]
    )
    msg.send()


@app.task
def send_online_notifications(online_notification_id, user_author_id, context):
    pass


@app.task
def send_webhook_notifications(webhook_notification_id, user_author_id, context):
    pass


@app.task
def send_notifications_task(**kwargs):
    event_email_notifications = EventEmailNotification.objects.filter(event_type__code=kwargs.get('event_code'))

    for event_email_notification in event_email_notifications:
        send_event_email_notifications.delay(
            event_email_notification_id=event_email_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )

    online_notifications = EventOnlineNotification.objects.filter(event_type__code=kwargs.get('event_code'))
    for online_notification in online_notifications:
        send_online_notifications.delay(
            online_notification_id=online_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )

    webhook_notifications = EventWebhookNotification.objects.filter(event_type__code=kwargs.get('event_code'))
    for webhook_notification in webhook_notifications:
        send_webhook_notifications.delay(
            webhook_notification_id=webhook_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )
