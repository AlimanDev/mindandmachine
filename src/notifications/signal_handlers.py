from django.dispatch import receiver

from src.events.signals import event_signal
from .tasks import send_notifications_task


@receiver(event_signal)
def send_notifications(sender, **kwargs):
    send_notifications_task.delay(
        event_code=kwargs.get('event_code'),
        network_id=kwargs.get('network_id'),
        user_author_id=kwargs.get('user_author_id'),
        context=kwargs.get('context'),
    )
