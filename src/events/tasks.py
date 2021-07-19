from src.celery.celery import app
from src.events.signals import event_signal
from django_celery_beat.models import CrontabSchedule
from datetime import datetime
from src.notifications.models import EventEmailNotification
from src.notifications.tasks import send_event_email_notifications


@app.task
def trigger_event(**kwargs):
    event_signal.send(sender=None, **kwargs)


@app.task
def cron_event():
    dttm = datetime.now()
    crons = CrontabSchedule.objects.all()
    posible_crons = []
    for cron in crons:
        schedule = cron.schedule
        if (
            dttm.minute in schedule.minute and
            dttm.hour in schedule.hour and
            dttm.weekday() in schedule.day_of_week and
            dttm.day in schedule.day_of_month and
            dttm.month in schedule.month_of_year
        ):
            posible_crons.append(cron)
    events = EventEmailNotification.objects.filter(
        report_config__cron__in=posible_crons,
    )
    for event_email_notification in events:
        dates = event_email_notification.report_config.get_dates()
        send_event_email_notifications.delay(
            event_email_notification_id=event_email_notification.id,
            user_author_id=None,
            context={
                'shop_ids': list(event_email_notification.report_config.shops.all().values_list('id', flat=True)),
                'dt_from': dates['dt_from'].strftime('%Y-%m-%dT%H:%M:%S'),
                'dt_to': dates['dt_to'].strftime('%Y-%m-%dT%H:%M:%S'),
            },
        )

