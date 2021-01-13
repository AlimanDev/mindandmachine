import os
from django.utils.timezone import now
from datetime import datetime, timedelta

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
from src.timetable.models import AttendanceRecords

from src.celery.celery import app


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.conf.djconfig")


@app.task()
def import_urv_zkteco():
    zkteco = ZKTeco()
    ext_system = ExternalSystem.objects.get(code='zkteco')

    max_date = AttendanceRecords.objects.aggregate(m=Max(F('dttm')))['m']
    if max_date:
        max_date -= timedelta(days=1)
    else:
        max_date=(datetime.now().date() - timedelta(days=30))

    dt_from=max_date.strftime("%Y-%m-%d 00:00:00")

    page = 0
    users = {}

    while True:
        page += 1
        events = zkteco.get_events(page=page, dt_from=dt_from)
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
            date = dttm.date()

            if user.id not in users:
                users[user.id] = {}
            if date not in users[user.id]:
                users[user.id][date] = {}
            if shop.id not in users[user.id][date]:
                users[user.id][date][shop.id] = {
                    'coming': dttm,
                    'leaving': dttm,
                }
            else:
                if users[user.id][date][shop.id]['coming'] > dttm:
                    users[user.id][date][shop.id]['coming'] = dttm
                if users[user.id][date][shop.id]['leaving'] < dttm:
                    users[user.id][date][shop.id]['leaving'] = dttm

    for user_id, dates in users.items():
        for date, vals in dates.items():
            for shop_id, times in vals.items():
                coming = AttendanceRecords.objects.filter(
                    dttm__date=date,
                    type=AttendanceRecords.TYPE_COMING,
                    user_id=user_id,
                    shop_id=shop_id,
                ).first()
                leaving = AttendanceRecords.objects.filter(
                    dttm__date=date,
                    type=AttendanceRecords.TYPE_LEAVING,
                    user_id=user_id,
                    shop_id=shop_id,
                ).first()
                if not coming:
                    print(f"create coming record {times['coming']} for {user_id} {shop_id}")
                    AttendanceRecords.objects.create(
                        dttm=times['coming'],
                        type=AttendanceRecords.TYPE_COMING,
                        user_id=user_id,
                        shop_id=shop_id,
                    )
                elif coming.dttm > times['coming']:
                    coming.dttm = times['coming']
                    coming.save()

                if times['leaving'] > times['coming']:
                    if not leaving:
                        print(f"create leaving record {times['leaving']} for {user_id} {shop_id}")
                        AttendanceRecords.objects.create(
                            dttm=times['leaving'],
                            type=AttendanceRecords.TYPE_LEAVING,
                            user_id=user_id,
                            shop_id=shop_id,
                        )
                    elif leaving.dttm < times['leaving']:
                        leaving.dttm = times['leaving']
                        leaving.save()


@app.task()
def export_workers_zkteco():
    zkteco=ZKTeco()
    ext_system = ExternalSystem.objects.get(code='zkteco')
    users = User.objects.all().exclude(userexternalcode__external_system=ext_system)

    for user in users:
        employments = Employment.objects.get_active(
            user.network_id,
            user=user,
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

        pin = user.id + 10000  # Чтобы не пересекалось с уже заведенными
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
    ext_system = ExternalSystem.objects.get(code='zkteco')
    users = User.objects.filter(userexternalcode__external_system=ext_system)

    dt_max = now().date()

    for user in users:
        employments = Employment.objects.get_active(
            user.network_id,
            user=user,
            position__isnull=False
        )
        if employments:
            continue

        user_code = UserExternalCode.objects.get(
            user=user,
            external_system=ext_system,
        )

        employments = Employment.objects.filter(
            user=user,
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
