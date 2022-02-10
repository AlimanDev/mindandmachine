from datetime import datetime, timedelta

from django.db.models import Q
from django_celery_beat.models import CrontabSchedule

from src.base.models import Employment, Shop, User, Employee
from src.celery.celery import app
from src.notifications.helpers import send_mass_html_mail
from src.reports.helpers import get_datatuple
from src.reports.models import ReportConfig
from .models import UserShopGroups, UserSubordinates


@app.task
def send_report_emails(report_config_id: int, zone: str):
    report_config = ReportConfig.objects.select_related(
        'report_type',
    ).get(
        id=report_config_id,
    )
    dates = report_config.get_dates(zone)
    context = {
        'dt_from': dates['dt_from'],
        'dt_to': dates['dt_to'],
        'shop_ids': list(report_config.shops.all().values_list('id', flat=True)),
        'period_step': report_config.get_acc_period()
    }
    message_content = report_config.email_text or ''
    subject = report_config.subject
    recipients = report_config.get_recipients(context)

    if report_config.email_addresses:
        recipients.extend(report_config.email_addresses.split(','))
    datatuple = []
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
            datatuple.extend(
                get_datatuple(recipients + emails, subject, message_content, report_config.get_file(context)))
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


@app.task
def fill_user_shop_groups(consider_position_groups=True, consider_function_groups=True, dt_from=None, dt_to=None):
    user_shop_groups_set = set()
    employments_qs = Employment.objects.get_active(
        dt_from=dt_from,
        dt_to=dt_to,
    ).select_related(
        'employee',
        'shop',
        'position__group',
        'function_group',
    )
    for employment in employments_qs:
        group_name = employment.position.group.name if \
            (
                        employment.position and employment.position.group and consider_position_groups) else employment.function_group.name if \
            (employment.function_group and consider_function_groups) else ''
        user_shop_groups_set.add(
            (
                employment.employee.user_id,
                employment.shop_id,
                group_name,
            ),
        )
        descendant_shop_ids = employment.shop.get_descendants(include_self=False).values_list('id', flat=True)
        for descendant_shop_id in descendant_shop_ids:
            user_shop_groups_set.add(
                (
                    employment.employee.user_id,
                    descendant_shop_id,
                    group_name,
                ),
            )

    UserShopGroups.objects.all().delete()
    objs = [UserShopGroups(
        user_id=usg[0],
        shop_id=usg[1],
        group_name=usg[2],
    ) for usg in user_shop_groups_set]
    UserShopGroups.objects.bulk_create(
        objs=objs,
        batch_size=10000,
    )


@app.task
def fill_user_subordinates(dt=None, dt_to_shift_days=None, use_user_shop_groups=False):
    user_subordinates = []
    for user in User.objects.all():
        subordinate_ids = user.get_subordinates(
            dt=dt,
            user_shops=UserShopGroups.objects.filter(
                user=user).values_list('shop_id', flat=True) if use_user_shop_groups else None,
            dt_to_shift=timedelta(days=dt_to_shift_days) if dt_to_shift_days else None,
        ).values_list('id', flat=True).distinct()
        for subordinate_id in subordinate_ids:
            user_subordinates.append(
                (
                    user.id,
                    subordinate_id,
                )
            )

    UserSubordinates.objects.all().delete()
    objs = [UserSubordinates(
        user_id=user_subordinate[0],
        employee_id=user_subordinate[1],
    ) for user_subordinate in user_subordinates]
    UserSubordinates.objects.bulk_create(
        objs=objs,
        batch_size=10000,
    )
