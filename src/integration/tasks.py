import os
from django.utils.timezone import now
from datetime import datetime, timedelta, date

from src.integration.zkteco import ZKTeco


from django.db.models import F, Max, ObjectDoesNotExist
from src.base.models import (
    Shop,
    Employment,
    User,
)
from src.integration.models import (
    ExternalSystem,
    UserExternalCode,
    ShopExternalCode,
)
from src.timetable.models import AttendanceRecords, WorkerDay

from src.celery.celery import app
from django.conf import settings


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.conf.djconfig")


@app.task()
def import_urv_zkteco():
    zkteco = ZKTeco()
    try:
        ext_system = ExternalSystem.objects.get(code='zkteco')
    except:
        raise ValueError('You need to create external system with code \'zkteco\'')

    max_date = AttendanceRecords.objects.aggregate(m=Max(F('dttm')))['m']
    if max_date:
        max_date -= timedelta(days=1)
    else:
        max_date=(datetime.now().date() - timedelta(days=30))

    dt_from=max_date.strftime("%Y-%m-%d 00:00:00")
    dt_to=(max_date + timedelta(31)).strftime("%Y-%m-%d 00:00:00") # в zkteco обязательна дата окончания

    page = 0
    users = {}

    while True:
        page += 1
        events = zkteco.get_events(page=page, dt_from=dt_from, dt_to=dt_to)
        if not events['data']:
            break

        for event in events['data']:
            try:
                shop_token = ShopExternalCode.objects.get(
                    code=event['accZone'],
                    external_system=ext_system)
            except ObjectDoesNotExist:
                print(f"Shop for event {event} does not exist")
                continue
            shop = shop_token.shop

            try:
                user_token = UserExternalCode.objects.get(
                    code=event['pin'],
                    external_system=ext_system)
            except ObjectDoesNotExist:
                print(f"User for shop {shop} event {event}  does not exist")
                continue
            user = user_token.user

            dttm = datetime.strptime(event['eventTime'], "%Y-%m-%d %H:%M:%S")

            if user.id not in users:
                users[user.id] = []
            users[user.id].append((dttm, shop))

    wds = WorkerDay.objects.filter(
        employee__user__in=users.keys(),
        dt__gte=max_date - timedelta(1),
        dt__lte=date.today() + timedelta(1),
        is_fact=False,
        is_approved=True,
        type_id__in=WorkerDay.TYPES_WITH_TM_RANGE,
    ).select_related('employee')

    worker_days = {}
    for wd in wds:
        worker_days.setdefault(wd.employee.user_id, {})[wd.dt] = wd

    attrs = AttendanceRecords.objects.filter(
        user_id__in=users.keys(),
        dt__gte=max_date - timedelta(1),
        dt__lte=date.today(),
    )
    attendance_records = {}
    for attr in attrs:
        attendance_records.setdefault(attr.user_id, {}).setdefault(attr.shop_id, {})[attr.dttm] = attr

    for user_id, dttms in users.items():
        dttms = sorted(dttms, key=lambda x: x[0])
        for dttm, shop in dttms:
            record = attendance_records.get(user_id, {}).get(shop.id, {}).get(dttm)
            if record: # если отметка уже внесена игнорируем
                continue
            AttendanceRecords.objects.create(
                user_id=user_id,
                dttm=dttm,
                shop=shop,
                terminal=True,
            )


@app.task()
def export_workers_zkteco():
    zkteco=ZKTeco()
    try:
        ext_system = ExternalSystem.objects.get(code='zkteco')
    except:
        raise ValueError('You need to create external system with code \'zkteco\'')
    users = User.objects.all().exclude(userexternalcode__external_system=ext_system)

    for user in users:
        employments = Employment.objects.get_active(
            user.network_id,
            employee__user=user,
            position__isnull=False,
        )
        if not employments:
            continue
        shop_ids = employments.values_list('shop_id')

        shop_code = ShopExternalCode.objects.filter(
            external_system=ext_system,
            shop__in=shop_ids
        ).first()

        if not shop_code:
            print(f'no external shop for {user}')
            continue

        e = employments.filter(
            shop_id=shop_code.shop_id,
        ).first()

        pin = user.id + settings.ZKTECO_USER_ID_SHIFT  # Чтобы не пересекалось с уже заведенными
        res = zkteco.add_user(e, pin)
        if 'code' in res and res['code'] == 0:
            user_code = UserExternalCode.objects.create(
                user=user,
                external_system=ext_system,
                code=pin
            )
            print(f'Added user {user} for employment{e} to zkteco with ext code {user_code.code}')

            res_area = zkteco.add_personarea(user_code,shop_code)
            if not('code' in res and res['code'] == 0):
                print(f'Error in {res_area} while set area for user {user}to zkteco')
        else:
            print(f'Error in {res} while saving user {user} to zkteco')


@app.task()
def delete_workers_zkteco():
    zkteco = ZKTeco()
    try:
        ext_system = ExternalSystem.objects.get(code='zkteco')
    except:
        raise ValueError('You need to create external system with code \'zkteco\'')
    users = User.objects.filter(userexternalcode__external_system=ext_system)

    dt_max = now().date()

    for user in users:
        employments = Employment.objects.get_active(
            user.network_id,
            employee__user=user,
            position__isnull=False
        )
        if employments:
            continue

        user_code = UserExternalCode.objects.get(
            user=user,
            external_system=ext_system,
        )

        employments = Employment.objects.filter(
            employee__user=user,
            dt_fired__lt=dt_max,
        )

        for e in employments:
            shop_code = ShopExternalCode.objects.filter(
                shop_id=e.shop_id,
                external_system=ext_system).first()
            if shop_code:
                res = zkteco.delete_personarea(user_code, shop_code)
                if 'code' in res and res['code'] == 0:
                    user_code.delete()
                    print(f"Delete area and userexternalcode for fired user {user} {e}")
                else:
                    print(f"Failed delete area and userexternalcode for fired user {e}: {res}")
