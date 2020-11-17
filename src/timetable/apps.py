from django.apps import AppConfig


class SrcTimetableConfig(AppConfig):
    name = 'src.timetable'

    def ready(self):
        from django.db.models.signals import post_migrate
        from .signal_handlers import create_worker_day_permissions
        post_migrate.connect(create_worker_day_permissions, sender=self)
