from src.adapters.celery.celery import app
from src.apps.events.signals import event_signal

@app.task
def trigger_event(**kwargs):
    event_signal.send(sender=None, **kwargs)
