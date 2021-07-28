from django.apps import AppConfig
from django.db.models.signals import post_migrate

class ReportsConfig(AppConfig):
    name = 'src.reports'
    def ready(self):
        from .signal_handlers import sync_report_types
        post_migrate.connect(sync_report_types, sender=self)
