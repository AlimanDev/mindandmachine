import datetime

from src.db.models import (
    WorkerDay,
    Timetable,
    AttendanceRecords,
)
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
        return datetime.datetime.strptime(obj, QOS_DATE_FORMAT).date()

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
    @classmethod
    def convert_main(cls, obj):
        return {
            'id': obj.id,
            'username': obj.username,
            'shop_id': obj.shop_id,
            'first_name': obj.first_name,
            'last_name': obj.last_name,
            'middle_name': obj.middle_name,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'sex': obj.sex,
            'phone_number': obj.phone_number,
            'email': obj.email,
            'tabel_code': obj.tabel_code,
        }

    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'username': obj.username,
            'shop_id': obj.shop_id,
            'first_name': obj.first_name,
            'last_name': obj.last_name,
            'middle_name': obj.middle_name,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'dt_hired': cls.convert_date(obj.dt_hired),
            'dt_fired': cls.convert_date(obj.dt_fired),
            'auto_timetable': obj.auto_timetable,
            'extra_info': obj.extra_info,
            'sex': obj.sex,
            'salary': float(obj.salary),
            'is_fixed_hours': obj.is_fixed_hours,
            'phone_number': obj.phone_number,
            'email': obj.email,
            'is_ready_for_overworkings': obj.is_ready_for_overworkings,
            'tabel_code': obj.tabel_code,
            'attachment_group': obj.attachment_group,
            'position': obj.position.title if hasattr(obj, 'position') and obj.position else '', # fixme: hasatrr always return true, => sometimes extra request to db
            'identifier': obj.identifier if hasattr(obj, 'identifier') else None,
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

        data = {
            'id': obj.id,
            'dttm_added': cls.convert_datetime(obj.dttm_added),
            'dt': cls.convert_date(obj.dt),
            'worker': obj.worker_id,
            'type': cls.convert_type(obj.type),
            'dttm_work_start': __work_tm(obj.dttm_work_start),
            'dttm_work_end': __work_tm(obj.dttm_work_end),
            'work_types': list(set(obj.work_types_ids)) if hasattr(obj, 'work_types_ids') else [],
            'work_type': obj.work_type_id if hasattr(obj, 'work_type_id') else None,
            'created_by': obj.created_by_id,
        }
        if hasattr(obj, 'other_shop'):
            data['other_shop']=  obj.other_shop

        return data


class WorkerDayChangeLogConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        def __work_tm(__field):
            return cls.convert_time(__field) if obj.type == WorkerDay.Type.TYPE_WORKDAY.value else None

        def __parent_work_tm(__tm):
            return cls.convert_time(__tm) if\
                obj.parent_worker_day and obj.parent_worker_day.type == WorkerDay.Type.TYPE_WORKDAY.value else None

        parent = obj.parent_worker_day
        if parent:
            return {
                'worker_day': obj.id,
                'dttm_changed': BaseConverter.convert_datetime(obj.dttm_added),
                'changed_by': obj.created_by.id,
                'comment': '',
                'from_tm_work_start': __parent_work_tm(parent.dttm_work_start),
                'from_tm_work_end': __parent_work_tm(parent.dttm_work_end),
                'from_type': WorkerDayConverter.convert_type(parent.type),
                'to_tm_work_start': __work_tm(obj.dttm_work_start),
                'to_tm_work_end': __work_tm(obj.dttm_work_end),
                'to_type': WorkerDayConverter.convert_type(obj.type),
            }
        else:
            return {}


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
            'dttm_work_start': __work_tm(obj.dttm_work_start),
            'dttm_work_end': __work_tm(obj.dttm_work_end),
        }


class WorkTypeConverter(BaseConverter):
    @classmethod
    def convert_operation_type(cls, obj):
        return {
            'id': obj.id,
            'name': obj.name,
            'speed_coef': obj.speed_coef,
            'do_forecast': obj.do_forecast,
            'work_type_id': obj.work_type.id
        }

    @classmethod
    def convert(cls, obj, convert_operations=False):
        converted_dict = {
            'id': obj.id,
            'dttm_added': cls.convert_datetime(obj.dttm_added),
            'dttm_deleted': cls.convert_datetime(obj.dttm_deleted),
            'shop': obj.shop_id,
            'priority': obj.priority,
            'name': obj.name,
            'prob': obj.probability,
            'prior_weight': obj.prior_weight,
            'min_workers_amount': obj.min_workers_amount,
            'max_workers_amount': obj.max_workers_amount,
        }
        if convert_operations:
            converted_dict['operation_types'] = [
                cls.convert_operation_type(x) for x in obj.work_type_reversed.filter(dttm_deleted__isnull=True)
            ]

        return converted_dict


class OperationTypeConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'name': obj.name,
            'speed_coef': obj.speed_coef,
            'do_forecast': obj.do_forecast,
            'work_type_id': obj.work_type.id
        }


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
            'work_type': obj.work_type_id,
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
            'week_length': obj.worker.week_availability,
            'weekday': obj.weekday,
            'tm': cls.convert_time(obj.tm),
            'is_lite': obj.is_lite,
        }


class PeriodClientsConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm_forecast': cls.convert_datetime(obj.dttm_forecast),
            'clients': obj.clients if hasattr(obj, 'clients') else obj.value,
            'type': obj.type,
            'work_type': obj.operation_type.work_type.id
        }


class PeriodDemandChangeLogConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm_from': cls.convert_datetime(obj.dttm_from),
            'dttm_to': cls.convert_datetime(obj.dttm_to),
            'operation_type': obj.operation_type.id,
            'work_type': obj.operation_type.work_type.id,
            'multiply_coef': obj.multiply_coef,
            'set_value': obj.set_value
        }


class ShopConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'parent': obj.parent_id,
            'title': obj.title,
            'tm_shop_opens': cls.convert_time(obj.tm_shop_opens),
            'tm_shop_closes': cls.convert_time(obj.tm_shop_closes),
            'code': obj.code,
            'address': obj.address,
            'type': obj.type,
            'dt_opened': cls.convert_date(obj.dt_opened),
            'dt_closed': cls.convert_date(obj.dt_closed),
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
            'dttm_added': BaseConverter.convert_datetime(obj.dttm_added),
            'to_worker': obj.to_worker_id,
            'was_read': obj.was_read,

            # 'type': obj.event.text,
            'text': obj.event.get_text() if obj.event_id else '',
            'is_question': obj.event.is_question() if obj.event_id else '',
            'is_action_active': obj.event.is_action_active() if obj.event_id else False,
            # 'object_id': obj.object_id,
            # 'content_type': obj._meta.object_name,
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


class UserWeekdaySlotConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'worker': obj.worker_id,
            'week_length': obj.worker.week_availability,
            'weekday': obj.weekday,
            'slot': SlotConverter.convert(obj.slot),
            'is_suitable': obj.is_suitable,
        }


class AttendanceRecordsConverter(BaseConverter):
    __TYPES = {
        AttendanceRecords.TYPE_COMING: 'пришел',
        AttendanceRecords.TYPE_LEAVING: 'ушел',
        AttendanceRecords.TYPE_BREAK_START: 'ушел на перерыв',
        AttendanceRecords.TYPE_BREAK_END: 'вернулся с перерыва',
    }

    @classmethod
    def convert_type(cls, obj):
        return cls.__TYPES.get(obj.type, '')

    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm': cls.convert_datetime(obj.dttm),
            'worker_id': obj.user_id,
            'type': obj.type,
            'is_verified': obj.verified,
        }


class ProductionDayConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dt': cls.convert_date(obj.dt),
            'type': obj.type,
            'is_celebration': obj.is_celebration,
        }


class VacancyConverter(BaseConverter):
    @classmethod
    def convert(self, obj):
        return {
            'id': obj.id,
            'dttm_added': self.convert_datetime(obj.dttm_added),
            'dt': self.convert_date(obj.dttm_from.date()),
            'dttm_from': self.convert_time(obj.dttm_from.time()),
            'dttm_to': self.convert_time(obj.dttm_to.time()),
            'worker_fio': obj.worker_day.worker.get_fio() if obj.worker_day_id else '',
            'is_canceled': True if obj.dttm_deleted else False,
            'work_type': obj.work_type_id,
        }
