import datetime

# todo: fix problem with time in 00:00
def timediff(tm_start, tm_end):
    """

    :param tm_start:
    :param tm_end:
    :return: time in hours
    """
    diff = (tm_end.hour - tm_start.hour) + (tm_end.minute - tm_start.minute) / 60
    if diff < 0:
        diff += 24
    return diff


def dttm_combine(dt, tm, stop_hours=None):
    if stop_hours is None:
        stop_hours = [0, 1, 2]
    dttm = datetime.datetime.combine(dt, tm)
    if tm.hour in stop_hours:
        dttm += datetime.timedelta(days=1)
    return dttm
