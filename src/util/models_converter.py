import datetime

from src.db.models import User, WorkerDay, PeriodDemand, Timetable, Notifications, CashboxType
from src.conf.djconfig import (
    QOS_DATE_FORMAT,
    QOS_DATETIME_FORMAT,
    QOS_TIME_FORMAT,
)


class BaseConverter(object):
    @classmethod
    def convert_date(cls, obj):
        return obj.strftime(QOS_DATE_FORMAT) if obj is not None else None

    @classmethod
    def parse_date(cls, obj):
        return datetime.datetime.strptime(obj, QOS_DATE_FORMAT)

    @classmethod
    def convert_time(cls, obj):
        return obj.strftime(QOS_TIME_FORMAT) if obj is not None else None

    @classmethod
    def parse_time(cls, obj):
        return datetime.datetime.strptime(obj, QOS_TIME_FORMAT).time()

    @classmethod
    def parse_datetime(cls, obj):
        return datetime.datetime.strptime(obj, QOS_DATETIME_FORMAT)

    @classmethod
    def convert_datetime(cls, obj):
        return obj.strftime(QOS_DATETIME_FORMAT) if obj is not None else None


class UserConverter(BaseConverter):
    __WORK_TYPE = {
        User.WorkType.TYPE_5_2.value: '52',
        User.WorkType.TYPE_2_2.value: '22',
        User.WorkType.TYPE_HOUR.value: 'H',
        User.WorkType.TYPE_SOS.value: 'S',
        User.WorkType.TYPE_MANAGER.value: 'M',
    }

    __WORK_TYPE_REVERSED = {v: k for k, v in __WORK_TYPE.items()}

    @classmethod
    def convert_work_type(cls, obj_type):
        return cls.__WORK_TYPE.get(obj_type, '')

    @classmethod
    def parse_work_type(cls, obj_type):
        return cls.__WORK_TYPE_REVERSED.get(obj_type)

    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'username': obj.username,
            'shop_id': obj.shop_id,
            'work_type': cls.convert_work_type(obj.work_type),
            'first_name': obj.first_name,
            'last_name': obj.last_name,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'dt_hired': cls.convert_date(obj.dt_hired),
            'dt_fired': cls.convert_date(obj.dt_fired),
            'auto_timetable': obj.auto_timetable,
            'comment': obj.extra_info,
            'sex': obj.sex,
            'is_fixed_hours': obj.is_fixed_hours,
            'is_fixed_days': obj.is_fixed_days,
            'phone_number': obj.phone_number,
            'is_ready_for_overworkings': obj.is_ready_for_overworkings,
            'tabel_code': obj.tabel_code,

        }


class WorkerDayConverter(BaseConverter):
    __WORKER_DAY_TYPE = {
        WorkerDay.Type.TYPE_HOLIDAY.value: 'H',
        WorkerDay.Type.TYPE_WORKDAY.value: 'W',
        WorkerDay.Type.TYPE_VACATION.value: 'V',
        WorkerDay.Type.TYPE_SICK.value: 'S',
        WorkerDay.Type.TYPE_QUALIFICATION.value: 'Q',
        WorkerDay.Type.TYPE_ABSENSE.value: 'A',
        WorkerDay.Type.TYPE_MATERNITY.value: 'M',
        WorkerDay.Type.TYPE_BUSINESS_TRIP.value: 'T',
        WorkerDay.Type.TYPE_ETC.value: 'O',
        WorkerDay.Type.TYPE_DELETED.value: 'D',
        WorkerDay.Type.TYPE_EMPTY.value: 'E',
    }

    __WORKER_DAY_TYPE_REVERSED = {v: k for k, v in __WORKER_DAY_TYPE.items()}

    @classmethod
    def convert_type(cls, obj_type):
        return cls.__WORKER_DAY_TYPE.get(obj_type, '')

    @classmethod
    def parse_type(cls, obj_type):
        return cls.__WORKER_DAY_TYPE_REVERSED.get(obj_type)

    @classmethod
    def convert(cls, obj):
        def __work_tm(__field):
            return cls.convert_time(__field) if obj.type == WorkerDay.Type.TYPE_WORKDAY.value else None

        return {
            'id': obj.id,
            'dttm_added': cls.convert_datetime(obj.dttm_added),
            'dt': cls.convert_date(obj.dt),
            'worker': obj.worker_id,
            'type': cls.convert_type(obj.type),
            'tm_work_start': __work_tm(obj.tm_work_start),
            'tm_work_end': __work_tm(obj.tm_work_end),
            'tm_break_start': __work_tm(obj.tm_break_start),
            'is_manual_tuning': obj.is_manual_tuning,
            'cashbox_types': list(set(obj.cashbox_types_ids)) if hasattr(obj, 'cashbox_types_ids') else [],
        }


class WorkerDayChangeRequestConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        def __work_tm(__field):
            return cls.convert_time(__field) if obj.type == WorkerDay.Type.TYPE_WORKDAY.value else None

        return {
            'id': obj.id,
            'dttm_added': cls.convert_datetime(obj.dttm_added),
            'worker_day': obj.worker_day_id,

            'type': WorkerDayConverter.convert_type(obj.type),
            'tm_work_start': __work_tm(obj.tm_work_start),
            'tm_work_end': __work_tm(obj.tm_work_end),
            'tm_break_start': __work_tm(obj.tm_break_start),
        }


class CashboxTypeConverter(BaseConverter):
    __FORECAST_TYPE = {
        CashboxType.FORECAST_HARD: 1,
        CashboxType.FORECAST_LITE: 2,
        CashboxType.FORECAST_NONE: 0,
    }

    __FORECAST_TYPE_REVERSED = {v: k for k, v in __FORECAST_TYPE.items()}

    @classmethod
    def convert_type(cls, obj_type):
        return cls.__FORECAST_TYPE.get(obj_type, '')

    @classmethod
    def convert(cls, obj, add_algo_params=False):
        vals = {
            'id': obj.id,
            'dttm_added': cls.convert_datetime(obj.dttm_added),
            'dttm_deleted': cls.convert_datetime(obj.dttm_deleted),
            'shop': obj.shop_id,
            'name': obj.name,
            'is_stable': obj.is_stable,
            'speed_coef': obj.speed_coef,
            'do_forecast': obj.do_forecast
        }
        if add_algo_params:
            vals.update({
                'prob': obj.probability,
                'prior_weight': obj.prior_weight,
                'prediction': cls.convert_type(obj.do_forecast),
            })
        return vals


class CashboxConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm_added': cls.convert_datetime(obj.dttm_added),
            'dttm_deleted': cls.convert_datetime(obj.dttm_deleted),
            'type': obj.type_id,
            'number': obj.number,
            'bio': obj.bio
        }


class WorkerCashboxInfoConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'worker': obj.worker_id,
            'cashbox_type': obj.cashbox_type_id,
            'mean_speed': obj.mean_speed,
            'bills_amount': obj.bills_amount,
            'period': obj.period,
            'priority': obj.priority,
            'duration': obj.duration
        }


class WorkerConstraintConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'worker': obj.worker_id,
            'weekday': obj.weekday,
            'tm': cls.convert_time(obj.tm)
        }


class PeriodDemandConverter(BaseConverter):
    __FORECAST_TYPE = {
        PeriodDemand.Type.SHORT_FORECAST.value: 'S',
        PeriodDemand.Type.LONG_FORECAST.value: 'L',
        PeriodDemand.Type.FACT.value: 'F'
    }

    __FORECAST_TYPE_REVERSED = {v: k for k, v in __FORECAST_TYPE.items()}

    @classmethod
    def convert_forecast_type(cls, obj_type):
        return cls.__FORECAST_TYPE.get(obj_type, '')

    @classmethod
    def parse_forecast_type(cls, obj_type):
        return cls.__FORECAST_TYPE_REVERSED.get(obj_type)

    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm_forecast': cls.convert_datetime(obj.dttm_forecast),
            'clients': obj.clients,
            'products': obj.products,
            'type': cls.convert_forecast_type(obj.type),
            'cashbox_type': obj.cashbox_type_id,
            'queue_wait_time': obj.queue_wait_time,
            'queue_wait_length': obj.queue_wait_length,
            'lack': obj.lack_of_cashiers,
        }


class PeriodDemandChangeLogConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm_from': cls.convert_datetime(obj.dttm_from),
            'dttm_to': cls.convert_datetime(obj.dttm_to),
            'cashbox_type': obj.cashbox_type_id,
            'multiply_coef': obj.multiply_coef,
            'set_value': obj.set_value
        }


class ShopConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'super_shop': obj.super_shop_id,
            'full_interface': obj.full_interface,
            'title': obj.title
        }


class SuperShopConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'title': obj.title,
            'code': obj.code,
            'dt_opened': obj.dt_opened,
            'dt_closed': obj.dt_closed
        }


class TimetableConverter(BaseConverter):
    __STATUSES = {
        Timetable.Status.READY.value: 'R',
        Timetable.Status.PROCESSING.value: 'P',
        Timetable.Status.ERROR.value: 'E'
    }

    __STATUSES_REVERSED = {v: k for k, v in __STATUSES.items()}

    @classmethod
    def convert_status(cls, status_obj):
        return cls.__STATUSES.get(status_obj, '')

    @classmethod
    def parse_status(cls, status_obj):
        return cls.__STATUSES_REVERSED.get(status_obj)

    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'shop': obj.shop_id,
            'dt': cls.convert_date(obj.dt),
            'status': cls.convert_status(obj.status),
            'dttm_status_change': cls.convert_datetime(obj.dttm_status_change)
        }


class NotificationConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'type': obj.type,
            'text': obj.text,
            'was_read': obj.was_read,
            'to_worker': obj.to_worker_id,
            'dttm_added': BaseConverter.convert_datetime(obj.dttm_added)
        }


class SlotConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'shop': obj.shop_id,
            'tm_start': cls.convert_time(obj.tm_start),
            'tm_end':  cls.convert_time(obj.tm_end),
            'name': obj.name
        }

