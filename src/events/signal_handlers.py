from django.dispatch import receiver

from .models import EventHistory, EventType
from .registry import EventRegistryHolder
from .signals import event_signal


@receiver(event_signal)
def write_event_history(sender, **kwargs):
    event_type = EventType.objects.filter(code=kwargs.get('event_code')).first()
    if event_type and event_type.write_history:
        EventHistory.objects.create(
            network_id=kwargs.get('network_id'),
            event_type=event_type,
            user_author_id=kwargs.get('user_author_id'),
            context=kwargs.get('context', {}),
        )


def sync_event_types(sender, **kwargs):
    for event_code, event_cls in EventRegistryHolder.get_registry().items():
        EventType.objects.update_or_create(
            code=event_code,
            defaults={
                'name': event_cls.name,
                'write_history': event_cls.write_history,
            }
        )
