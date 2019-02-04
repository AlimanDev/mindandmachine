import datetime

from src.db.models import (
    User,
    WorkerDay,
    Timetable,
    WorkType,
    UserIdentifier,
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
        user_identifier = UserIdentifier.objects.filter(worker_id=obj.id).first()
        return {
            'id': obj.id,
            'username': obj.username,
            'shop_id': obj.shop_id,
            'work_type': cls.convert_work_type(obj.work_type),
            'first_name': obj.first_name,
            'last_name': obj.last_name,
            'middle_name': obj.middle_name,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'dt_hired': cls.convert_date(obj.dt_hired),
            'dt_fired': cls.convert_date(obj.dt_fired),
            'auto_timetable': obj.auto_timetable,
            'comment': obj.extra_info,
            'sex': obj.sex,
            'is_fixed_hours': obj.is_fixed_hours,
            'is_fixed_days': obj.is_fixed_days,
            'phone_number': obj.phone_number,
            'email': obj.email,
            'is_ready_for_overworkings': obj.is_ready_for_overworkings,
            'tabel_code': obj.tabel_code,
            'group': obj.group,
            'attachment_group': obj.attachment_group,
            'identifier': user_identifier.identifier if user_identifier else None,
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
            'dttm_work_start': __work_tm(obj.dttm_work_start),
            'dttm_work_end': __work_tm(obj.dttm_work_end),
            'work_types': list(set(obj.work_types_ids)) if hasattr(obj, 'work_types_ids') else [],
            'created_by': obj.created_by_id,
        }


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
            'weekday': obj.weekday,
            'tm': cls.convert_time(obj.tm)
        }


class PeriodClientsConverter(BaseConverter):
    @classmethod
    def convert(cls, obj):
        return {
            'id': obj.id,
            'dttm_forecast': cls.convert_datetime(obj.dttm_forecast),
            'clients': obj.value,
            'type': obj.type,
            'work_type': obj.work_type_id
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
            'address': obj.address,
            'type': obj.type,
            'region': obj.region.title if obj.region else None,
            'dt_opened': cls.convert_date(obj.dt_opened),
            'dt_closed': cls.convert_date(obj.dt_closed),
            'tm_start': cls.convert_time(obj.tm_start),
            'tm_end': cls.convert_time(obj.tm_end),
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
            'dttm_added': BaseConverter.convert_datetime(obj.dttm_added),
            'object_id': obj.object_id,
            'content_type': obj.content_type.__str__()
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
            'worker_id': obj.identifier.worker_id,
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