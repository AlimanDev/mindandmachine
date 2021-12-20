import json

from django.db.models import Subquery, Q, OuterRef, F
from src.timetable.models import PlanAndFactHours, WorkerDay
from datetime import timedelta, datetime, date
from src.base.models import Shop, User, Employment
from src.recognition.api.recognition import Recognition
from src.recognition.models import UserConnecter
from src.recognition.events import DUPLICATE_BIOMETRICS
from src.events.signals import event_signal
from django.conf import settings


def get_worker_days_with_no_ticks(dttm: datetime):
    '''
    Смотрим рабочие дни, с момента начала или окончания прошло не более 5 минут
    '''
    dttm = dttm.replace(second=0, microsecond=0)

    no_comming = []
    no_leaving = []
    pfh_qs = PlanAndFactHours.objects.annotate(
        employment_shop_id=Subquery(
            Employment.objects.filter(
                Q(dt_fired__isnull=True) | Q(dt_fired__gte=OuterRef('dt')),
                Q(dt_hired__isnull=True) | Q(dt_hired__lte=OuterRef('dt')),
                employee_id=OuterRef('employee_id'),
            ).values('shop_id')[:1]
        ),
    ).select_related(
        'shop',
        'shop__director',
        'worker',
    )

    for shop in Shop.objects.select_related('network').all():
        dttm_to = dttm + timedelta(hours=shop.get_tz_offset())
        dttm_from_comming = dttm_to - timedelta(seconds=json.loads(shop.network.settings_values).get('delta_for_comming_in_secs', 300))
        dttm_from_leaving = dttm_to - timedelta(seconds=json.loads(shop.network.settings_values).get('delta_for_leaving_in_secs', 300))
        no_comming.extend(
            list(
                pfh_qs.filter(
                    dttm_work_start_plan__gte=dttm_from_comming, 
                    dttm_work_start_plan__lt=dttm_from_comming + timedelta(minutes=1), 
                    ticks_comming_fact_count=0,
                    wd_type_id=WorkerDay.TYPE_WORKDAY,
                    shop=shop,
                )
            )
        )
        no_leaving.extend(
            list(
                pfh_qs.filter(
                    dttm_work_end_plan__gte=dttm_from_leaving, 
                    dttm_work_end_plan__lt=dttm_from_leaving + timedelta(minutes=1), 
                    ticks_leaving_fact_count=0,
                    wd_type_id=WorkerDay.TYPE_WORKDAY,
                    shop=shop,
                )
            )
        )
    return no_comming, no_leaving


def check_duplicate_biometrics(image, user: User, shop_id):
    r = Recognition()
    person_id = r.identify(image)
    if person_id:
        try:
            user_connecter = UserConnecter.objects.get(partner_id=person_id)
        except UserConnecter.DoesNotExist:
            return 'User from other system'
        if user.id == user_connecter.user_id:
            return
        user2 = user_connecter.user
        active_employments = Employment.objects.get_active(
            dt_from=date.today(), 
            dt_to=date.today(),
        ).select_related('employee')
        employment1 = active_employments.filter(employee__user=user).first()\
        or Employment.objects.filter(employee__user=user).select_related('employee').order_by('-dt_fired').first()
        employment2 = active_employments.filter(employee__user=user2).first()\
        or Employment.objects.filter(employee__user=user2).select_related('employee').order_by('-dt_fired').first()
        event_signal.send(
            sender=None,
            network_id=user.network_id,
            event_code=DUPLICATE_BIOMETRICS,
            user_author_id=None,
            shop_id=shop_id,
            context={
                'fio1': f"{user.last_name} {user.first_name}",
                'fio2': f"{user2.last_name} {user2.first_name}",
                'url1': settings.EXTERNAL_HOST + user.avatar.url,
                'url2': settings.EXTERNAL_HOST + user2.avatar.url,
                'tabel_code1': employment1.employee.tabel_code if employment1 else user.username,
                'tabel_code2': employment2.employee.tabel_code if employment2 else user2.username,
                'shop1': employment1.shop.name if employment1 else 'Без отдела',
                'shop2': employment2.shop.name if employment2 else 'Без отдела',
            },
        )
