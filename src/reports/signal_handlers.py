from src.reports.registry import ReportRegistryHolder
from src.base.models import Network
from src.reports.models import ReportType



def sync_report_types(sender, **kwargs):
    for network in Network.objects.all():
        for event_code, event_cls in ReportRegistryHolder.get_registry().items():
            ReportType.objects.update_or_create(
                network=network,
                code=event_code,
                defaults={
                    'name': event_cls.name,
                }
            )
