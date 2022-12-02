from typing import Union
from datetime import date, datetime, timedelta
import calendar

from faker.providers.date_time import Provider


def _time_to_float(t):
    return t.hour + t.minute / 60 + t.second / 3600

class DateTimeHelper:
    """General purpose date/time functions"""
    provider = Provider(generator=None)

    @classmethod
    def to_dt(cls, date: Union[str, datetime, date]) -> date:
        """Converts relative date str to date (e.g. `-1d`, `today`, `now`, `+3m`), datetime to date. Date is unchanged."""
        return cls.provider._parse_date(date)

    @staticmethod
    def last_month_dt_pair() -> tuple[date, date]:
        """Last month's first and last days"""
        dt_last = date.today().replace(day=1) - timedelta(1)
        dt_first = dt_last.replace(day=1)
        return dt_first, dt_last
