from src.db.models import WorkerDay


class BaseConverter(object):
    @classmethod
    def _convert_date(cls, obj):
        return obj.strftime('%d.%m.%Y') if obj is not None else None

    @classmethod
    def _convert_time(cls, obj):
        return obj.strftime('%H:%M:%S') if obj is not None else None

    @classmethod
    def _convert_datetime(cls, obj):
        return obj.strftime('%H:%M:%S %d.%m.%Y') if obj is not None else None


class UserConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'first_name': obj.first_name,
            'last_name': obj.last_name,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'dt_hired': cls._convert_date(obj.dt_hired),
            'dt_fired': cls._convert_date(obj.dt_fired),
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
            return cls._convert_time(__field) if obj.type == WorkerDay.Type.TYPE_WORKDAY.value else None

        return {
            'id': obj.id,
            'dttm_added': cls._convert_datetime(obj.dttm_added),
            'dt': cls._convert_date(obj.dt),
            'worker': obj.worker_id,
            'type': cls.convert_type(obj.type),
            'tm_work_start': __work_tm(obj.tm_work_start),
            'tm_work_end': __work_tm(obj.tm_work_end),
            'tm_break_start': __work_tm(obj.tm_break_start),
            'is_manual_tuning': obj.is_manual_tuning
        }


class WorkerDayChangeRequestConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        def __work_tm(__field):
            return cls._convert_time(__field) if obj.type == WorkerDay.Type.TYPE_WORKDAY.value else None

        return {
            'id': obj.id,
            'dttm_added': cls._convert_datetime(obj.dttm_added),
            'worker_day': obj.worker_day_id,

            'type': WorkerDayConverter.convert_type(obj.type),
            'tm_work_start': __work_tm(obj.tm_work_start),
            'tm_work_end': __work_tm(obj.tm_work_end),
            'tm_break_start': __work_tm(obj.tm_break_start),
        }


class WorkerDayChangeLogConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        def __work_tm(__field, __type):
            return cls._convert_time(__field) if __type == WorkerDay.Type.TYPE_WORKDAY.value else None

        return {
            'id': obj.id,
            'dttm_changed': cls._convert_datetime(obj.dttm_changed),
            'worker_day': obj.worker_day_id,

            'from_type': WorkerDayConverter.convert_type(obj.from_type),
            'from_tm_work_start': __work_tm(obj.from_tm_work_start, obj.from_type),
            'from_tm_work_end': __work_tm(obj.from_tm_work_end, obj.from_type),
            'from_tm_break_start': __work_tm(obj.from_tm_break_start, obj.from_type),

            'to_type': WorkerDayConverter.convert_type(obj.to_type),
            'to_tm_work_start': __work_tm(obj.to_tm_work_start, obj.to_type),
            'to_tm_work_end': __work_tm(obj.to_tm_work_end, obj.to_type),
            'to_tm_break_start': __work_tm(obj.to_tm_break_start, obj.to_type),

            'changed_by': obj.changed_by_id
        }


class CashboxTypeConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm_added': cls._convert_datetime(obj.dttm_added),
            'dttm_deleted': cls._convert_datetime(obj.dttm_deleted),
            'shop': obj.shop_id,
            'name': obj.name
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
            'dt_period_end': cls._convert_date(obj.dt_period_end)
        }


class WorkerConstraintConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'worker': obj.worker_id,
            'weekday': obj.weekday,
            'tm': cls._convert_time(obj.tm),
            'is_active': obj.is_active
        }
