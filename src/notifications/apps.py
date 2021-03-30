from django.apps import AppConfig


class SrcNotificationsConfig(AppConfig):
    name = 'src.notifications'

    def ready(self):
        from .signal_handlers import send_notifications  # noqa