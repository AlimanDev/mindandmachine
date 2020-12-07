from django.core.mail import EmailMultiAlternatives
from django.core.mail import get_connection

from src.celery.celery import app
from .models import EventEmailNotification


@app.task
def send_event_email_notifications(event_email_notification_id, user_author_id, context):
    event_email_notification = EventEmailNotification.objects.select_related(
        'event_type', 'smtp_server_settings',
    ).get(
        id=event_email_notification_id
    )
    connection = get_connection(
        backend='django.core.mail.backends.console.EmailBackend',
        **event_email_notification.smtp_server_settings.get_smtp_server_settings()
    )
    msg = EmailMultiAlternatives(
        connection=connection,
        subject='test',
        body='test',
        from_email=['from@email.com'],
        to=event_email_notification.get_recipients(),
    )
    # msg.send()
