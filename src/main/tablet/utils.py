from datetime import datetime, time as datetime_time, timedelta
import datetime as dt


def time_diff(start, end):
    """
    difference between 2 times taking into account midnight switch
    :param start: start_time
    :param end: end_time
    :return: timedelta object in seconds
    """
    if isinstance(start, datetime_time):
        assert isinstance(end, datetime_time)
        start, end = [datetime.combine(datetime.min, t) for t in [start, end]]
    if start <= end:
        return (end - start).total_seconds()
    else:
        end += timedelta(1)
        assert end > start
        return (end - start).total_seconds()


def is_midnight_period(dttm_now):
    """
    :param dttm_now: current date and time
    :return: True if time is less than 6 a.m, false -- otherwise
    """

    tm_shop_opens = dt.time(6, 0)

    return True if dttm_now.time() < tm_shop_opens else False

