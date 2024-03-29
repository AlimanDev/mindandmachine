import typing as tp
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings
from faker.providers.date_time import Provider


def _time_to_float(t):
    return t.hour + t.minute / 60 + t.second / 3600

class DateTimeHelper:
    """General purpose date/time functions"""
    provider = Provider(generator=None)

    @classmethod
    def to_dt(cls, date: str | datetime | date) -> date:
        """Converts relative date str to date (e.g. `-1d`, `today`, `now`, `+3m`), datetime to date. Date is unchanged."""
        return cls.provider._parse_date(date)

    @staticmethod
    def to_dt_str(date: str | datetime | date) -> str:
        if isinstance(date, str):
            return date
        return date.strftime(settings.QOS_DATE_FORMAT)

    @staticmethod
    def to_dttm_str(datetime: str | datetime | date) -> str:
        if isinstance(datetime, str):
            return datetime
        return datetime.strftime(settings.QOS_DATETIME_FORMAT)

    @staticmethod
    def last_month_dt_pair() -> tuple[date, date]:
        """Last month's first and last days"""
        dt_last = date.today().replace(day=1) - timedelta(1)
        dt_first = dt_last.replace(day=1)
        return dt_first, dt_last

    @staticmethod
    def first_day_next_month(dt: date) -> date:
        """First day in the next month"""
        first_day = dt.replace(day=1)
        if first_day.month == 12:
            return first_day.replace(year=first_day.year+1, month=1)
        else:
            return first_day.replace(month=dt.month+1)

    @classmethod
    def last_day_in_month(cls, dt: date) -> date:
        """Last day in current month"""
        return cls.first_day_next_month(dt) - timedelta(1)


class BaseDateProducer(ABC):
    def __init__(self, **kwrgs):
        ...

    @abstractmethod
    def produce(self, **kwargs) -> date:
        ...


class NowDateTimeProducer(BaseDateProducer):

    def produce(self, **kwargs) -> date:
        return date.today()


class MonthOffsetTimeProducer(BaseDateProducer):

    def produce(self, **kwargs) -> date:
        try:
            month_offset =int(kwargs['month_offset'])
        except KeyError as exc:
            raise KeyError(
                'MonthOffsetTimeProducer.produce requires month_offset as int kwarg'
            ) from exc
        try:
            day_offset =int(kwargs['day_offset'])
        except KeyError as exc:
            raise KeyError(
                'MonthOffsetTimeProducer.produce requires day_offset as int kwarg'
            ) from exc
        out = (date.today() + relativedelta(months=month_offset)).replace(day=1)
        out += timedelta(days=day_offset)
        return  out
    

class PredefinedDateProducer(BaseDateProducer):
    def __init__(self, d: str, **kwargs):
        self.d = datetime.strptime(d, settings.QOS_DATE_FORMAT)
    def produce(self, **kwargs) -> date:
        return self.d


class DateProducerFactory:
    @staticmethod
    def get_factory(frmt: str, class_kwargs: tp.Optional[dict] = None) -> BaseDateProducer:
        if class_kwargs is None:
            class_kwargs = dict()
        
        if frmt in DT_FACTORIES:
            out = DT_FACTORIES[frmt](**class_kwargs)
        else:
            raise KeyError(f'Date time producer of {frmt} is not supported')
        return out


DT_FACTORIES = {
    "now": NowDateTimeProducer,
    "month_start_with_offset": MonthOffsetTimeProducer,
    "predefined": PredefinedDateProducer
}