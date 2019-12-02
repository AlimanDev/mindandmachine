from datetime import datetime, time as datetime_time, timedelta
import datetime as dt

from src.db.models import WorkerDayCashboxDetails, WorkerDay


def time_diff(start, end):
    """
    Разница между двумя временами с учетом перехода через полночь

    Args:
        start (datetime.time): начало
        end (datetime.time): конец

    Returns:
        int: количество секунд между двумя временами
    """
    if isinstance(start, datetime_time):
        assert isinstance(end, datetime_time)
        start, end = [datetime.combine(datetime.min, t) for t in [start, end]]
    if start <= end:
        return (end - start).total_seconds()
    elif start > end and (start-end).seconds <= 10:  # костыль из-за set_interval на фронте
        return (start - end).total_seconds()

    else:
        end += timedelta(1)
        assert end > start
        return (end - start).total_seconds()


def is_midnight_period(dttm_now):
    """
    Проверяет полночь ли сейчас

    Args:
        dttm_now(QOS_DATETIME): дата-время

    Returns:
        bool: True если время меньше 6 утра, иначе -- False
    """

    tm_shop_opens = dt.time(6, 0)

    return True if dttm_now.time() < tm_shop_opens else False


def get_status_and_details(worker_id, dttm):
    """
    Получаем какую-то полезную инфу о worker_day_cashbox_details

    Args:
        worker_id (int): id работника
        dttm (datetime.datetime): datetime -- date -- day, time -- current time

    Returns:
        (tuple): tuple содержащий:
            day_detail (WorkerDayCashboxDetails): последний объект в QuerySet'e
            worker_day (WorkerDay): соответствующий worker_day
            status (WorkerDayCashboxDetails.status): статус
    """

    status = ''
    worker_day = None

    day_detail = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        worker_day__dt=dt,
        worker_day__worker_id=worker_id
    ).order_by('id').last()

    if not day_detail is None:
        worker_day = day_detail.worker_day

        if day_detail.is_tablet:
            if not day_detail.tm_to is None:
                status = WorkerDayCashboxDetails.TYPE_FINISH
            else:
                status = day_detail.status
        else:
            day_detail = None

    if day_detail is None:
        if worker_day.type == WorkerDay.TYPE_ABSENSE:
            status = WorkerDayCashboxDetails.TYPE_ABSENCE
        elif worker_day.type == WorkerDay.TYPE_WORKDAY and \
                (dt.datetime.combine(worker_day.dt, worker_day.tm_work_start) < dttm):
            status = WorkerDayCashboxDetails.TYPE_SOON
        else:
            status = WorkerDayCashboxDetails.TYPE_T
    return status, day_detail, worker_day