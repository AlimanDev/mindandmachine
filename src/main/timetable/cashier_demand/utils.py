from src.db.models import WorkerDay


def filter_worker_day_by_dttm(shop_id, day_type, dttm_from, dttm_to):
    dt_from = dttm_from.date()
    tm_from = dttm_from.time()
    dt_to = dttm_to.date()
    tm_to = dttm_to.time()

    days_raw = WorkerDay.objects.filter(
        worker_shop_id=shop_id,
        type=day_type,
        dt__gte=dt_from,
        dt__lte=dt_to,
    )

    days = []
    for d in days_raw:
        if d.dt == dt_from and d.tm_work_end < tm_from:
            continue
        if d.dt == dt_to and d.tm_work_start > tm_to:
            continue

        days.append(d)

    return days
