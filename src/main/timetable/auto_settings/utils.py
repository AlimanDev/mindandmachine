from datetime import datetime, timedelta
from django.conf import settings


def time2int(tm, minute_step=15, start_h=6):
    """
    Вообще непонятно что функция делает

    Todo:
        Исправить(даже скорее переписать).
    Args:
        tm(datetime.time):
        minute_step(int):
        start_h(int):
    Returns:
        хз что вообще
    """
    diff_h = tm.hour - start_h
    if diff_h < 0:
        diff_h += 24
    return int((diff_h * 60 + tm.minute) / minute_step + 0.99999999)

def set_timetable_date_from(year, month):
    date_from = datetime(year=year, month=month, day=1).date()
    date_min = datetime.now().date() + timedelta(days=settings.REBUILD_TIMETABLE_MIN_DELTA)
    date_mon_begin = datetime(year=date_min.year, month=date_min.month, day=1).date()

    if date_from < date_mon_begin:
        return None
    if date_from < date_min:
        date_from = date_min
    return date_from
