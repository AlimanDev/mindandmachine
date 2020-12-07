from django.dispatch import receiver

from src.events.signals import event_signal
from .models import (
    EventEmailNotification,
    # EventOnlineNotification,
    # EventWebhookNotification,
)
from .tasks import send_event_email_notifications


@receiver(event_signal)
def send_notifications(sender, **kwargs):
    event_email_notifications = EventEmailNotification.objects.filter(
        network_id=kwargs.get('network_id'), event_type__code=kwargs.get('event_code'),
    )
    # online_notifications = EventOnlineNotification.objects.filter(event_type__code=event_code)
    # webhook_notifications = EventWebhookNotification.objects.filter(event_type__code=event_code)

    for event_email_notification in event_email_notifications:
        send_event_email_notifications.delay(
            event_email_notification_id=event_email_notification.id,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context'),
        )
