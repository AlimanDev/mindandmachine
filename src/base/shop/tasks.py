from datetime import datetime, timedelta

import pandas as pd
from django.conf import settings
from django.db.models import Q
from tzwhere import tzwhere

from src.base.models import ShopSchedule, Shop
from src.celery.celery import app
from src.util.models_converter import Converter


@app.task
def fill_shop_schedule(shop_id, dt_from, periods=90):
    """
    Заполнение ShopSchedule стандартным расписанием на опред. период
    :param shop_id: id магазина
    :param dt_from: дата от (включительно)
    :param periods: на сколько дней вперед заполнить расписания от dt_from
    :return:
    """
    if isinstance(dt_from, str):
        dt_from = Converter.parse_date(dt_from)

    shop = Shop.objects.get(id=shop_id)

    existing_shop_schedule_dict = {
        ss.dt: ss for ss in
        ShopSchedule.objects.filter(
            shop_id=shop_id,
            dt__gte=dt_from,
            dt__lte=dt_from + timedelta(days=periods),
        )
    }
    skipped = 0
    to_create = []
    to_update = []
    for dt in pd.date_range(dt_from, periods=periods, normalize=True):
        dt = dt.date()
        existing_shop_schedule = existing_shop_schedule_dict.get(dt)

        if not existing_shop_schedule:
            to_create.append(dt)
            continue

        if existing_shop_schedule.modified_by_id is not None:
            skipped += 1
            continue

        standard_schedule = shop.get_standard_schedule(dt)

        if standard_schedule is None:  # выходной по стандартному расписанию
            if existing_shop_schedule.type != ShopSchedule.HOLIDAY_TYPE \
                    or existing_shop_schedule.opens is not None or existing_shop_schedule.closes is not None:
                to_update.append((dt, (ShopSchedule.HOLIDAY_TYPE, None, None)))
                continue
        else:
            if standard_schedule['tm_open'] != existing_shop_schedule.opens \
                    or standard_schedule['tm_close'] != existing_shop_schedule.closes:
                to_update.append(
                    (dt, (ShopSchedule.WORKDAY_TYPE, standard_schedule['tm_open'], standard_schedule['tm_close']))
                )
                continue

        skipped += 1

    if to_create:
        shop_schedules_to_create = []
        for dt in to_create:
            standard_schedule = shop.get_standard_schedule(dt=dt)
            shop_schedules_to_create.append(
                ShopSchedule(
                    shop_id=shop_id,
                    dt=dt,
                    opens=standard_schedule['tm_open'] if standard_schedule else None,
                    closes=standard_schedule['tm_close'] if standard_schedule else None,
                    type=ShopSchedule.WORKDAY_TYPE if standard_schedule else ShopSchedule.HOLIDAY_TYPE,
                )
            )
        ShopSchedule.objects.bulk_create(shop_schedules_to_create)

    if to_update:
        for dt, (schedule_type, opens, closes) in to_update:
            ShopSchedule.objects.update_or_create(
                shop_id=shop_id,
                dt=dt,
                defaults={
                    'type': schedule_type,
                    'opens': opens,
                    'closes': closes,
                },
            )

    return {'created': len(to_create), 'updated': len(to_update), 'skipped': skipped}


@app.task
def fill_shop_city_from_coords(shop_id):
    shop = Shop.objects.filter(id=shop_id).first()
    if shop and shop.latitude and shop.longitude and settings.DADATA_TOKEN:
        from dadata import Dadata
        dadata = Dadata(settings.DADATA_TOKEN)
        result = dadata.geolocate(name="address", lat=float(shop.latitude), lon=float(shop.longitude))
        if result and result[0].get('data') and result[0].get('data').get('city'):
            shop.city = result[0]['data']['city']
            shop.save(update_fields=['city'])


@app.task
def fill_city_coords_address_timezone_from_fias_code(shop_id):
    shop = Shop.objects.filter(id=shop_id).first()
    if shop and shop.fias_code and settings.DADATA_TOKEN:
        from dadata import Dadata
        dadata = Dadata(settings.DADATA_TOKEN)
        result = dadata.find_by_id("fias", shop.fias_code)
        if result and result[0].get('data'):
            update_fields = []
            if result[0].get('value'):
                shop.address = result[0].get('value')
                update_fields.append('address')
            data = result[0].get('data')
            if data.get('city'):
                shop.city = result[0]['data']['city']
                update_fields.append('city')
            if data.get('geo_lat'):
                shop.latitude = data.get('geo_lat')
                update_fields.append('latitude')
            if data.get('geo_lon'):
                shop.longitude = data.get('geo_lon')
                update_fields.append('longitude')
            if data.get('geo_lat') and data.get('geo_lon'):
                tz = tzwhere.tzwhere()
                timezone = tz.tzNameAt(float(data.get('geo_lat')), float(data.get('geo_lon')))
                if timezone:
                    shop.timezone = timezone
                else:
                    tz = tzwhere.tzwhere(forceTZ=True)
                    timezone = tz.tzNameAt(float(data.get('geo_lat')), float(data.get('geo_lon')), forceTZ=True)
                    shop.timezone = timezone
                update_fields.append('timezone')
            if update_fields:
                shop.save(update_fields=update_fields)


@app.task
def fill_active_shops_schedule():
    res = {}
    dttm_now = datetime.now()
    dt_now = dttm_now.date()
    active_shops_qs = Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gt=dttm_now),
        Q(dt_closed__isnull=True) | Q(dt_closed__gt=dt_now),
    )
    for shop_id in active_shops_qs.values_list('id', flat=True):
        res[shop_id] = fill_shop_schedule(shop_id, dt_now)

    return res
