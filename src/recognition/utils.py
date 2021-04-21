from src.timetable.models import PlanAndFactHours, WorkerDay
from datetime import timedelta, datetime, date
from src.base.models import Shop, User, Employment
from src.recognition.api.recognition import Recognition
from src.recognition.models import UserConnecter
from src.recognition.events import DUPLICATE_BIOMETRICS
from src.notifications.models.event_notification import EventEmailNotification
from src.events.signals import event_signal
from django.conf import settings


def get_worker_days_with_no_ticks(dttm: datetime):
    '''
    Смотрим рабочие дни, с момента начала или окончания прошло не более 5 минут
    '''
    dttm = dttm.replace(second=0, microsecond=0)

    no_comming = []
    no_leaving = []

    for shop in Shop.objects.all():
        dttm_to = dttm + timedelta(hours=shop.get_tz_offset())
        dttm_from = dttm_to - timedelta(minutes=5)
        no_comming.extend(
            list(
                PlanAndFactHours.objects.filter(
                    dttm_work_start_plan__gte=dttm_from, 
                    dttm_work_start_plan__lt=dttm_to, 
                    ticks_comming_fact_count=0,
                    wd_type=WorkerDay.TYPE_WORKDAY,
                    shop=shop,
                ).select_related(
                    'shop',
                    'shop__director',
                    'worker',
                )
            )
        )
        no_leaving.extend(
            list(
                PlanAndFactHours.objects.filter(
                    dttm_work_end_plan__gte=dttm_from, 
                    dttm_work_end_plan__lt=dttm_to, 
                    ticks_leaving_fact_count=0,
                    wd_type=WorkerDay.TYPE_WORKDAY,
                    shop=shop,
                ).select_related(
                    'shop',
                    'shop__director',
                    'worker',
                )
            )
        )
    return no_comming, no_leaving


def check_duplicate_biometrics(image, user: User):
    from src.celery.tasks import send_event_email_notifications
    r = Recognition()
    person_id = r.identify(image)
    if person_id:
        try:
            user_connecter = UserConnecter.objects.get(person_id=person_id)
        except UserConnecter.DoesNotExist:
            return 'User from other system'
        if user.id == user_connecter.user_id:
            return
        user2 = user_connecter.user
        active_employments = Employment.objects.get_active(
            dt_from=date.today(), 
            dt_to=date.today(),
        )
        employment1 = active_employments.filtter(user=user).first() or Employment.objects.filter(user=user).order_by('-dttm_fired').first()
        employment2 = active_employments.filtter(user=user2).first() or Employment.objects.filter(user=user2).order_by('-dttm_fired').first()
        event_signal.send(
            sender=None,
            network_id=user.network_id,
            event_code=DUPLICATE_BIOMETRICS,
            user_author_id=None,
            context={
                'fio1': f"{user.last_name} {user.first_name}",
                'fio2': f"{user2.last_name} {user2.last_name}",
                'url1': settings.HOST + user.avatar.url,
                'url2': settings.HOST + user2.avatar.url,
                'tabel_code1': (employment1.tabel_code if employment1 else user.tabel_code) or user.username,
                'tabel_code2': (employment2.tabel_code if employment2 else user2.tabel_code) or user2.username,
            },
        )
