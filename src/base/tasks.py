from django.conf import settings

from src.celery.celery import app
from .models import (
    Network,
    ApiLog,
)


@app.task()
def clean_api_log():
    for network in Network.objects.all():
        ApiLog.clean_log(
            network_id=network.id,
            delete_gap=network.settings_values_prop.get(
                'api_log_settings', {}).get('delete_gap', settings.API_LOG_DELETE_GAP),
        )
