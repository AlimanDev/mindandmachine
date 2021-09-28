from src.base.models import Employment, Shop
from src.notifications.helpers import send_mass_html_mail
from src.celery.celery import app
from django_celery_beat.models import CrontabSchedule
from django.db.models import Q
from datetime import datetime
from src.reports.models import ReportConfig
from src.reports.helpers import get_datatuple

@app.task
def send_report_emails(report_config_id: int, zone: str):
    report_config = ReportConfig.objects.select_related(
        'report_type',
    ).get(
        id=report_config_id,
    )
    message_content = report_config.email_text or ''
    subject = report_config.subject
    recipients = report_config.get_recipients()

    if report_config.email_addresses:
        recipients.extend(report_config.email_addresses.split(','))
    datatuple = []
    dates = report_config.get_dates(zone)
    context = {
        'dt_from': dates['dt_from'],
        'dt_to': dates['dt_to'],
        'shop_ids': list(report_config.shops.all().values_list('id', flat=True)),
        'period_step': report_config.get_acc_period()
    }
    if report_config.send_by_group_employments_shops:
        groups = list(report_config.groups.all())
        employments = Employment.objects.get_active().filter(
            Q(function_group__in=groups) | Q(position__group__in=groups),
            employee__user__email__isnull=False,
        ).select_related('employee__user')
        employments_by_shops = {}
        for e in employments:
            employments_by_shops.setdefault(e.shop_id, []).append(e)
        for shop_id, employments in employments_by_shops.items():
            # пока что только дочерние магазины
            shops = Shop.objects.get(id=shop_id).get_descendants(include_self=False).values_list('id', flat=True)
            emails = [e.employee.user.email for e in employments]
            context['shop_ids'] = list(shops) or [shop_id]
            datatuple.extend(get_datatuple(recipients + emails, subject, message_content, report_config.get_file(context)))
    else:
        datatuple = get_datatuple(recipients, subject, message_content, report_config.get_file(context))

    send_mass_html_mail(datatuple=datatuple)


@app.task
def cron_report():
    dttm_now = datetime.utcnow()
    crons = CrontabSchedule.objects.all()
    posible_crons = []
    for cron in crons:
        schedule = cron.schedule
        dttm = dttm_now + cron.timezone.utcoffset(dttm_now)
        if (
            dttm.minute in schedule.minute and
            dttm.hour in schedule.hour and
            dttm.weekday() in schedule.day_of_week and
            dttm.day in schedule.day_of_month and
            dttm.month in schedule.month_of_year
        ):
            posible_crons.append(cron)
    reports = ReportConfig.objects.filter(
        cron__in=posible_crons,
        is_active=True,
    ).select_related('cron')
    for report in reports:
        send_report_emails.delay(
            report_config_id=report.id,
            zone=report.cron.timezone.zone,
        )
