import datetime

from src.conf.djconfig import (
    QOS_DATE_FORMAT,
    QOS_DATETIME_FORMAT,
    QOS_TIME_FORMAT,
)

from src.base.models import (
    Employment,
    User
)
from src.timetable.models import (
    WorkerDay,
)
from django.db import models

class Converter:
    @staticmethod
    def convert_date(obj):
        return obj.strftime(QOS_DATE_FORMAT) if obj is not None else None

    @staticmethod
    def parse_date(obj):
        return datetime.datetime.strptime(obj, QOS_DATE_FORMAT).date()

    @staticmethod
    def convert_time(obj):
        return obj.strftime(QOS_TIME_FORMAT) if obj is not None else None

    @staticmethod
    def parse_time(obj):
        return datetime.datetime.strptime(obj, QOS_TIME_FORMAT).time()

    @staticmethod
    def parse_datetime(obj):
        return datetime.datetime.strptime(obj, QOS_DATETIME_FORMAT)

    @staticmethod
    def convert_datetime(obj):
        return obj.strftime(QOS_DATETIME_FORMAT) if obj is not None else None

    @staticmethod
    def convert_queryset(elements, ModelClass, fields):
        fields = [] if not fields else fields
        values_dict = {}
        tmp_fields = fields.copy()
         # Получаем названия особенных полей
        for field in fields:
            if field.find('__') > 0:
                values_dict[field.replace('__', '_')] = models.F(field)
                tmp_fields.remove(field)
        fields = tmp_fields
        if fields or values_dict:
            elements = elements.values(*fields, **values_dict)
        else:
            elements = elements.values()
        return list(elements)

    @classmethod
    def convert_list(self, elements, ModelClass, fields, custom_converters):
        special_converters = custom_converters if custom_converters else {}            
        result = []
        for element in elements:
            el = {}
            for field in fields:
                convert_function = special_converters.get(field, lambda x: x)
                rel_fields = field.split('__')
                field_name = field
                if len(rel_fields) == 1:
                    el[field_name.replace('__', '_')] = convert_function(getattr(element, field_name))
                else:
                    try:
                        tmp_obj = element
                        for name in rel_fields[:-1]:
                            tmp_obj = getattr(tmp_obj, name)
                        el[field_name.replace('__', '_')] = convert_function(getattr(tmp_obj, rel_fields[-1]))
                    except AttributeError:
                        el[field_name.replace('__', '_')] = None
            result.append(el)
        return result  

    @classmethod
    def convert(self, elements, ModelClass=None, fields=None, custom_converters=None, out_array=False):
        '''
        Функция для преобразования данных из базы данных в формат json
        elements:list, tuple, QuerySet - данные
        ModelClass - класс модели, которую конвертируем
        fields: list - поля из модели, которые должны быть в результирующем json
        custom_converters: dict - словарь, где ключом является название поля, а значением
        функция которая применяется к нему
        out_array: bool - на выходе должен быть список даже если элемент один
        '''
        if not isinstance(elements, (list, tuple, models.QuerySet)):
            elements = [elements]
        if len(elements) == 0:
            return []
        # В случае наследования для сложных данных
        if hasattr(self, 'convert_function'):
            elements = [
                self.convert_function(element)
                for element in elements
            ]
        #Для простого конвертирования
        elif ModelClass:
            if isinstance(elements, models.QuerySet):
                elements = self.convert_queryset(elements, ModelClass, fields)
            else:
                elements = self.convert_list(elements, ModelClass, fields, custom_converters)

        return elements if len(elements) > 1 or out_array else elements[0]


class EmploymentConverter(Converter):
    @classmethod
    def convert_function(cls, obj: Employment):
        user = obj.user
        res = UserConverter.convert(user)
        res.update({
            'shop_id': obj.shop_id,
            'dt_hired': cls.convert_date(obj.dt_hired),
            'dt_fired': cls.convert_date(obj.dt_fired),
            'auto_timetable': obj.auto_timetable,
            'salary': float(obj.salary),
            'is_fixed_hours': obj.is_fixed_hours,
            'is_ready_for_overworkings': obj.is_ready_for_overworkings,
            'tabel_code': obj.tabel_code,
            'position': obj.position.name if obj.position_id is not None else '',
            'position_id': obj.position_id if obj.position_id is not None else '',
        })

        return res


class UserConverter(Converter):
    @classmethod
    def convert_function(cls, obj: User):
        return {
            'id': obj.id,
            'username': obj.username,
            'first_name': obj.first_name,
            'last_name': obj.last_name,
            'middle_name': obj.middle_name,
            'avatar_url': obj.avatar.url if obj.avatar else None,
            'sex': obj.sex,
            'phone_number': obj.phone_number,
            'email': obj.email,
        }


class WorkerDayConverter(Converter):

    @classmethod
    def convert_function(cls, obj):
        def __work_tm(__field):
            return cls.convert_time(__field) if obj.type == WorkerDay.TYPE_WORKDAY else None

        data = {
            'id': obj.id,
            'dttm_added': cls.convert_datetime(obj.dttm_added),
            'dt': cls.convert_date(obj.dt),
            'worker': obj.worker_id,
            'type': obj.type,
            'dttm_work_start': __work_tm(obj.dttm_work_start),
            'dttm_work_end': __work_tm(obj.dttm_work_end),
            'work_types': [w.id for w in obj.work_types.all()] if obj.id else [],
            'work_type': obj.work_type_id if hasattr(obj, 'work_type_id') else None,
            'created_by': obj.created_by_id,
            'comment': obj.comment,
            'worker_day_approve_id': obj.worker_day_approve_id,
        }
        if hasattr(obj, 'other_shop'):
            data['other_shop'] = obj.other_shop

        return data


class WorkerDayChangeLogConverter(Converter):
    @classmethod
    def convert_function(cls, obj):
        def __work_tm(__field):
            return cls.convert_time(__field) if obj.type == WorkerDay.TYPE_WORKDAY else None

        def __parent_work_tm(__tm):
            return cls.convert_time(__tm) if\
                obj.parent_worker_day and obj.parent_worker_day.type == WorkerDay.TYPE_WORKDAY else None

        parent = obj.parent_worker_day
        res = {}
        if parent or obj.created_by_id:
            res = {
                'worker_day': obj.id,
                'dttm_changed': Converter.convert_datetime(obj.dttm_added),
                'changed_by': obj.created_by_id,
                'change_by_fio': obj.created_by.last_name + ' ' + obj.created_by.first_name if obj.created_by_id else '',
                'comment': obj.comment,
                'to_tm_work_start': __work_tm(obj.dttm_work_start),
                'to_tm_work_end': __work_tm(obj.dttm_work_end),
                'to_type': obj.type,
            }
            if parent:
                res['from_tm_work_start'] = __parent_work_tm(parent.dttm_work_start)
                res['from_tm_work_end'] = __parent_work_tm(parent.dttm_work_end)
                res['from_type'] = parent.type
            else:
                res['from_type'] = WorkerDay.TYPE_EMPTY

        return res


class WorkTypeConverter(Converter):
    @classmethod
    def convert_operation_type(cls, obj):
        return {
            'id': obj.id,
            'name': obj.operation_type_name.name,
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
            'name': obj.work_type_name.name,
            'probability': obj.probability, #change front and algo
            'prior_weight': obj.prior_weight,
            'min_workers_amount': obj.min_workers_amount,
            'max_workers_amount': obj.max_workers_amount,
        }
        if convert_operations:
            converted_dict['operation_types'] = [
                cls.convert_operation_type(x) for x in obj.work_type_reversed.filter(dttm_deleted__isnull=True)
            ]

        return converted_dict



#TODO change front and algo "week_length" -> "employment__week_availability" constraints_info and availability_info


class NotificationConverter(Converter):
    @classmethod
    def convert_function(cls, obj):
        return {
            'id': obj.id,
            'dttm_added': Converter.convert_datetime(obj.dttm_added),
            'to_worker': obj.to_worker_id,
            'was_read': obj.was_read,

            # 'type': obj.event.text,
            'text': obj.event.get_text() if obj.event_id else '',
            'is_question': obj.event.is_question() if obj.event_id else '',
            'is_action_active': obj.event.is_action_active() if obj.event_id else False,
            # 'object_id': obj.object_id,
            # 'content_type': obj._meta.object_name,
        }


class VacancyConverter(Converter):
    @classmethod
    def convert_function(self, obj):
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
