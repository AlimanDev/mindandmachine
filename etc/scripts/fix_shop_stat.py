from datetime import timedelta

from django.db.models import Q, Exists, OuterRef

from src.timetable.models import ShopMonthStat, WorkerDay


def fix_shop_month_stat_is_approved():
    ShopMonthStat.objects.filter(is_approved=False).annotate(
        approved_wd_exists=Exists(WorkerDay.objects.filter(
            Q(shop_id=OuterRef('shop_id')) | Q(employment__shop_id=OuterRef('shop_id')),
            is_approved=True,
            is_fact=False,
            dt__gte=OuterRef('dt'),
            dt__lte=OuterRef('dt') + timedelta(days=30),  # примерно) под-другому быстро запрос не получилось сделать
        )),
    ).filter(
        approved_wd_exists=True,
    ).update(
        is_approved=True,
    )
