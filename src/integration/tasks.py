import os
from django.db.models.expressions import Exists, OuterRef
from django.utils.timezone import now
from datetime import datetime, timedelta, date

from src.integration.zkteco import ZKTeco


from django.db.models import F, Max
from src.base.models import (
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
    ext_system, _created = ExternalSystem.objects.get_or_create(code='zkteco')
    if _created:
        print('Created external system with code \'zkteco\'')

    max_date = AttendanceRecords.objects.aggregate(m=Max(F('dttm')))['m']
    if max_date:
        max_date -= timedelta(days=1)
    else:
        max_date=(datetime.now().date() - timedelta(days=30))

    dt_from=max_date.strftime("%Y-%m-%d 00:00:00")
    dt_to=(max_date + timedelta(31)).strftime("%Y-%m-%d 00:00:00") # в zkteco обязательна дата окончания

    page = 0
    users = {}

    wds = WorkerDay.objects.filter(
        employee__user__in=users.keys(),
        dt__gte=max_date - timedelta(1),
        dt__lte=date.today() + timedelta(1),
        is_fact=False,
        is_approved=True,
        type__is_dayoff=False,
    ).select_related('employee', 'shop')

    worker_days = {}
    for wd in wds:
        worker_days.setdefault(wd.employee.user_id, {})[wd.dt] = wd

    while True:
        page += 1
        events = zkteco.get_events(page=page, dt_from=dt_from, dt_to=dt_to)
        if not events['data']:
            break

        for event in events['data']:
            try:
                user_token = UserExternalCode.objects.get(
                    code=event['pin'],
                    external_system=ext_system)
            except UserExternalCode.DoesNotExist:
                print(f"User for event {event} does not exist")
                continue
            user_id = user_token.user_id
            dttm = datetime.strptime(event['eventTime'], "%Y-%m-%d %H:%M:%S")
            wd = worker_days.get(user_id, {}).get(dttm.date)
            if wd and ShopExternalCode.objects.filter(shop_id=wd.shop_id, attendance_area__code=event['accZone'], attendance_area__external_system=ext_system).exists():
                shop = wd.shop
            else:
                shop_ids = Employment.objects.get_active(
                    None,
                    dttm, dttm,
                    employee__user_id=user_id,
                    position__isnull=False,
                ).values_list('shop_id', flat=True)
                shop_token = ShopExternalCode.objects.filter(
                    attendance_area__code=event['accZone'],
                    attendance_area__external_system=ext_system,
                    shop_id__in=shop_ids,
                ).first() or ShopExternalCode.objects.filter(
                    attendance_area__code=event['accZone'],
                    attendance_area__external_system=ext_system,
                ).first()
                if shop_token:
                    shop = shop_token.shop
                else:
                    print(f"Shop for event {event} does not exist")
                    continue

            users.setdefault(user_id, []).append((dttm, shop))

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
    ext_system, _created = ExternalSystem.objects.get_or_create(code='zkteco')
    if _created:
        print('Created external system with code \'zkteco\'')
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

        shop_codes = ShopExternalCode.objects.filter(
            attendance_area__external_system=ext_system,
            shop__in=shop_ids
        )

        if not shop_codes:
            print(f'no external shop for {user}')
            continue

        pin = user.id + settings.ZKTECO_USER_ID_SHIFT  # Чтобы не пересекалось с уже заведенными
        res = zkteco.add_user(user, pin)
        if 'code' in res and res['code'] == 0:
            user_code = UserExternalCode.objects.create(
                user=user,
                external_system=ext_system,
                code=pin
            )
            print(f'Added user {user} to zkteco with ext code {user_code.code}')

            for shop_code in shop_codes:
                res_area = zkteco.add_personarea(user_code, shop_code.attendance_area)
                if not('code' in res and res['code'] == 0):
                    print(f'Error in {res_area} while set area for user {user} to zkteco')
        else:
            print(f'Error in {res} while saving user {user} to zkteco')


@app.task()
def delete_workers_zkteco():
    zkteco = ZKTeco()
    ext_system, _created = ExternalSystem.objects.get_or_create(code='zkteco')
    if _created:
        print('Created external system with code \'zkteco\'')
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

        employments = Employment.objects.annotate(
            has_active_empl=Exists(
                Employment.objects.get_active(
                    employee_id=OuterRef('employee_id'),
                    shop_id=OuterRef('shop_id')
                )
            )
        ).filter(
            employee__user=user,
            dt_fired__lt=dt_max,
            has_active_empl=False,
        )

        for e in employments:
            shop_codes = ShopExternalCode.objects.filter(
                shop_id=e.shop_id,
                attendance_area__external_system=ext_system,
            ).select_related('attendance_area')
            if shop_codes:
                for shop_code in shop_codes:
                    res = zkteco.delete_personarea(user_code, shop_code.attendance_area)
                    if 'code' in res and res['code'] == 0:
                        user_code.delete()
                        print(f"Delete area and userexternalcode for fired user {user} {e}")
                    else:
                        print(f"Failed delete area and userexternalcode for fired user {e}: {res}")


@app.task
def sync_att_area_zkteco():
    zkteco = ZKTeco()
    ext_system, _created = ExternalSystem.objects.get_or_create(code='zkteco')
    if _created:
        print('Created external system with code \'zkteco\'')

    page = 0

    while True:
        page += 1
        areas = zkteco.get_attarea_list(page=page)
        if not areas['data']:
            break
        for area in areas['data']:
            area, _ = AttendanceArea.objects.update_or_create(
                code=area["code"],
                external_system=ext_system,
                defaults={
                    'name': area['name'],
                }
            )
            print(f"Sync attendance area {area.name} with code {area.code}")
