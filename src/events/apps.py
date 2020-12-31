from django.apps import AppConfig

from django.db.models.signals import post_migrate


class SrcEventsConfig(AppConfig):
    name = 'src.events'

    def ready(self):
        from .signal_handlers import sync_event_types
        post_migrate.connect(sync_event_types, sender=self)
