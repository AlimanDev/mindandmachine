from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings

from src.base.models import Shop
from src.celery.celery import app
from src.timetable.models import ShopMonthStat
from src.timetable.work_type.utils import ShopEfficiencyGetter


@app.task
def update_shop_stats(dt=None):
    if not dt:
        dt = date.today().replace(day=1)
    else:
        dt = dt.replace(day=1)
    shops = list(Shop.objects.filter(dttm_deleted__isnull=True, child__isnull=True))
    month_stats = list(ShopMonthStat.objects.filter(shop__in=shops, shop__child__isnull=True, dt=dt))
    if len(shops) != len(month_stats):
        shops_with_stats = list(ShopMonthStat.objects.filter(
            shop__child__isnull=True,
            shop__in=shops,
            dt=dt,
        ).values_list('shop_id', flat=True))
        ShopMonthStat.objects.bulk_create(
            [
                ShopMonthStat(
                    shop=shop,
                    dt=dt,
                    dttm_status_change=datetime.now(),
                )
                for shop in shops
                if shop.id not in shops_with_stats
            ]
        )
        month_stats = list(ShopMonthStat.objects.filter(shop__in=shops, shop__child__isnull=True, dt=dt))
    for month_stat in month_stats:
        # if month_stat.status not in [ShopMonthStat.READY, ShopMonthStat.NOT_DONE]:
        #     continue

        if settings.UPDATE_SHOP_STATS_WORK_TYPES_CODES:
            work_type_ids = list(month_stat.shop.work_types.filter(
                work_type_name__code__in=settings.UPDATE_SHOP_STATS_WORK_TYPES_CODES,
            ).values_list('id', flat=True))
        else:
            work_type_ids = []
        stats = ShopEfficiencyGetter(
            shop_id=month_stat.shop_id,
            from_dt=month_stat.dt,
            to_dt=month_stat.dt + relativedelta(months=1, days=-1),
            work_type_ids=work_type_ids,
            indicators=True,
            efficiency=False,
        ).get()['indicators']
        month_stat.idle = stats['deadtime']
        month_stat.fot = stats['fot']
        month_stat.lack = stats['covering']  # на самом деле покрытие
        month_stat.predict_needs = stats['predict_needs']
        month_stat.save()


@app.task
def update_shop_stats_2_months():
    dt = date.today().replace(day=1)
    update_shop_stats(dt=dt)
    update_shop_stats(dt=dt + relativedelta(months=1))
