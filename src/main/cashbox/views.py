import datetime
import json

from src.base.models import (
    Shop,
)
from src.timetable.models import (
    WorkType,
    Cashbox,
    Slot,
)
from src.forecast.models import (
    OperationType,
)

from src.util.forms import FormUtil
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import (
    WorkTypeConverter,
    CashboxConverter,
    OperationTypeConverter,
)
from .forms import (
    GetTypesForm,
    GetCashboxesForm,
    CreateCashboxForm,
    DeleteCashboxForm,
    UpdateCashboxForm,
    CreateWorkTypeForm,
    EditWorkTypeForm,
    DeleteWorkTypeForm,
    CashboxesOpenTime,
)

from src.main.tablet.utils import time_diff
from src.main.other.notification.utils import send_notification
from django.db import IntegrityError


@api_method('GET', GetTypesForm)
def get_types(request, form):
    """
    Возвращает список рабочих типов касс для данного магазина

    Args:
        method: GET
        url: /api/cashbox/get_types
        shop_id(int): required = False
    Returns:
        [
            {
                | 'id': work_type_id,
                | 'dttm_deleted': дата удаления(здесь везде null),
                | 'shop': shop_id,
                | 'dttm_added': дата добавления,
                | 'speed_coef': int,
                | 'name': имя типа
            },...
        ]
    """
    shop_id = form['shop_id']

    types = WorkType.objects.filter(
        shop_id=shop_id,
        dttm_deleted__isnull=True,
    )
    return JsonResponse.success([
        WorkTypeConverter.convert(x, True) for x in types
    ])


@api_method('GET', GetCashboxesForm)
def get_cashboxes(request, form):
    """
    Возвращает список касс для заданных в work_types_ids типов

    Args:
        method: GET
        url: api/cashbox/get_cashboxes
        shop_id(int): required = False
        from_dt(QOS_DATE): required = False
        to_dt(QOS_DATE): required = False
        work_type_ids(list): список типов касс

    Returns:
        {
            'work_types':{
                work_type_id: {
                    | 'dttm_deleted': дата-время удаления (null),
                    | 'dttm_added': дата-время добавления,
                    | 'shop': shop_id,
                    | 'id': id типа кассы,
                    | 'name': имя типа кассы,
                    | 'speed_coef': int
                }
            },\n
            'cashboxes': [
                {
                    | 'dttm_deleted': ,
                    | 'dttm_added': ,
                    | 'number'(str): номер кассы,
                    | 'id': id кассы,
                    | 'type': id типа кассы,
                    | 'bio'(str): биография лол?
                }, ...
            ]
        }
    """
    shop_id = form['shop_id']
    dt_from = FormUtil.get_dt_from(form)
    dt_to = FormUtil.get_dt_to(form)
    work_type_ids = form['work_type_ids']

    work_types = WorkType.objects.qos_filter_active(
        dt_from,
        dt_to,
        shop_id=shop_id,
    )
    if len(work_type_ids) > 0:
        work_types = work_types.filter(id__in=work_type_ids)

    work_types = list(work_types.order_by('id'))

    cashboxes = Cashbox.objects.filter(
        type__id__in=list(map(lambda x: x.id, work_types)),
        dttm_deleted__isnull=True,
    ).order_by('number', 'id')

    return JsonResponse.success({
        'work_types': {x.id: WorkTypeConverter.convert(x) for x in work_types},
        'cashboxes': [CashboxConverter.convert(x) for x in cashboxes]
    })


@api_method(
    'POST',
    CreateCashboxForm,
    lambda_func=lambda x: WorkType.objects.get(id=x['work_type_id']).shop
)
def create_cashbox(request, form):
    """
    Создает новую кассу

    Args:
        method: POST
        url: /api/cashbox/create_cashbox
        work_type_id(int): id типа кассы, к которой будет привязана созданная касса
        number(str): номер кассы

    Returns:
        {
            'work_type': {
                | 'id': id типа кассы,
                | 'dttm_added': ,
                | 'dttm_deleted': ,
                | 'shop': shop_id,
                | 'name': название типа кассы,
                | 'speed_coef': int
            },\n
            'cashbox': {
                | 'id': id созданной кассы,
                | 'dttm_added': ,
                | 'dttm_deleted': null,
                | 'type': id типа кассы,
                | 'number'(str): номер,
                | 'bio'(str): лол
            }
        }

    Note:
        Отправляет уведомление о созданной кассе
    """
    work_type_id = form['work_type_id']
    cashbox_number = form['number']

    try:
        work_type = WorkType.objects.get(id=work_type_id)
    except WorkType.DoesNotExist:
        return JsonResponse.does_not_exists_error('work_type does not exist')

    cashboxes_count = Cashbox.objects.select_related(
        'type'
    ).filter(
        type__shop_id=work_type.shop_id,
        dttm_deleted=None,
        number=cashbox_number,
        type_id=work_type_id
    ).count()

    if cashboxes_count > 0:
        return JsonResponse.already_exists_error('Касса с таким номером уже существует')

    cashbox = Cashbox.objects.create(type=work_type, number=cashbox_number)

    send_notification('C', cashbox, sender=request.user)

    return JsonResponse.success({
        'work_type': WorkTypeConverter.convert(work_type),
        'cashbox': CashboxConverter.convert(cashbox)
    })


@api_method(
    'POST',
    DeleteCashboxForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def delete_cashbox(request, form):
    """
    "Удаляет" кассу с заданным номером

    Args:
        method: POST
        url: /api/cashbox/delete_cashbox
        shop_id(int): required = True
        work_type_id(int): required = True
        number(str): номер кассы которую удаляем
        bio(str): доп инфа

    Returns:
        {
            | 'id': id удаленной кассы,
            | 'dttm_added': ,
            | 'dttm_deleted': datetime.now(),
            | 'type': id типа кассы,
            | 'number': номер,
            | 'bio': доп инфа
        }

    Note:
        Отправляет уведомление об удаленной кассе
    """
    shop_id = form['shop_id']

    try:
        cashbox = Cashbox.objects.select_related(
            'type'
        ).get(
            type__id=form['work_type_id'],
            type__shop_id=shop_id,
            dttm_deleted=None,
            number=form['number']
        )
    except Cashbox.DoesNotExist:
        return JsonResponse.does_not_exists_error()
    except Cashbox.MultipleObjectsReturned:
        return JsonResponse.multiple_objects_returned()

    cashbox.dttm_deleted = datetime.datetime.now()
    cashbox.bio = form['bio']
    cashbox.save()

    send_notification('D', cashbox, sender=request.user)

    return JsonResponse.success(
        CashboxConverter.convert(cashbox)
    )


@api_method(
    'POST',
    UpdateCashboxForm,
    lambda_func=lambda x: WorkType.objects.get(id=x['to_work_type_id']).shop
)
def update_cashbox(request, form):
    """
    Меняет тип кассы у кассы с заданным номером

    Args:
        method: POST
        url: /api/cashbox/update_cashbox
        from_work_type_id(int): с какого типа меняем
        to_work_type_id(int): на какой
        number(str): номер кассы

    Returns:
        {
            | 'id': id,
            | 'dttm_added': ,
            | 'dttm_deleted': ,
            | 'type': id типа,
            | 'number': номер,
            | 'bio': доп инфа
        }

    Raises:
        JsonResponse.does_not_exists_error: если тип кассы с from/to_work_type_id не существует\
        или если кассы с заданным номером и привязанной к данному типу не существует
        JsonResponse.multiple_objects_returned: если вернулось несколько объектов в QuerySet'e

    """
    cashbox_number = form['number']

    try:
        from_work_type = WorkType.objects.get(id=form['from_work_type_id'])
    except WorkType.DoesNotExist:
        return JsonResponse.does_not_exists_error('from_work_type')

    try:
        to_work_type = WorkType.objects.get(id=form['to_work_type_id'])
    except WorkType.DoesNotExist:
        return JsonResponse.does_not_exists_error('to_work_type')

    try:
        cashbox = Cashbox.objects.select_related(
            'type'
        ).get(
            type__id=from_work_type.id,
            type__shop_id=from_work_type.shop_id,
            dttm_deleted=None,
            number=cashbox_number
        )
    except Cashbox.DoesNotExist:
        return JsonResponse.does_not_exists_error('cashbox')
    except Cashbox.MultipleObjectsReturned:
        return JsonResponse.multiple_objects_returned()

    cashbox.dttm_deleted = datetime.datetime.now()
    cashbox.save()

    cashbox = Cashbox.objects.create(type=to_work_type, number=cashbox_number)

    return JsonResponse.success(
        CashboxConverter.convert(cashbox)
    )


@api_method('POST', CreateWorkTypeForm)
def create_work_type(request, form):
    """
    Создает тип касс с заданным именем

    Args:
        method: POST
        url: /api/cashbox/create_work_type
        shop_id(int): required = True
        name(str): max_length=128

    Note:
        Также отправлет уведомление о том, что тип касс был создан

    Returns:
        {
            | 'id': id новой созданной кассы,
            | 'dttm_added': дата добавления,
            | 'dttm_deleted': null,
            | 'shop': id shop'a,
            | 'name': имя,
            | 'speed_coef': 1
        }

    Raises:
        JsonResponse.already_exists_error: если тип касс с таким именем уже существует
    """
    shop_id = form['shop_id']
    name = form['name']

    if WorkType.objects.filter(name=name, shop_id=shop_id, dttm_deleted__isnull=True).count() > 0:
        return JsonResponse.already_exists_error('Такой тип работ уже существует')

    new_work_type = WorkType.objects.create(
        name=name,
        shop_id=shop_id,
    )

    send_notification('C', new_work_type, sender=request.user)

    return JsonResponse.success(WorkTypeConverter.convert(new_work_type))


@api_method(
    'POST',
    DeleteWorkTypeForm,
    lambda_func=lambda x: WorkType.objects.get(id=x['work_type_id']).shop
)
def delete_work_type(request, form):
    """
    Удаляет тип касс с заданным id'шником

    Args:
        method: POST
        url: /api/cashbox/delete_work_type
        work_type_id(int): required = True

    Note:
        Также отправлет уведомление о том, что тип работ был удален

    Returns:
        {
            | 'id': id новой созданной кассы,
            | 'dttm_added': дата добавления,
            | 'dttm_deleted': дата удаления(сейчас),
            | 'shop': id shop'a,
            | 'name': имя
        }

    Raises:
        JsonResponse.internal_error: если к данному типу касс привязаны какие-то кассы
    """
    work_type = WorkType.objects.get(id=form['work_type_id'])

    attached_cashboxes = Cashbox.objects.filter(type=work_type, dttm_deleted__isnull=True)

    if attached_cashboxes.count() > 0:
        return JsonResponse.internal_error('there are cashboxes on this type')

    work_type.dttm_deleted = datetime.datetime.now()
    work_type.save()

    send_notification('D', work_type, sender=request.user)

    return JsonResponse.success(WorkTypeConverter.convert(work_type))


@api_method(
    'POST',
    EditWorkTypeForm,
    lambda_func=lambda x: WorkType.objects.get(id=x['work_type_id']).shop
)
def edit_work_type(request, form):
    err_operation = 'Указаны неверные данные для операций или типа работ. Обязательно укажите время нормативы по операциям.'
    err_slot = 'Указаны неверные данные для смены. Проверьте время начала и окончания смены.'

    work_type_id = form['work_type_id']
    work_type = WorkType.objects.get(id=work_type_id)
    shop_id = work_type.shop_id

    worker_amount = form['workers_amount']
    if worker_amount:
        work_type.min_workers_amount = worker_amount[0]
        work_type.max_workers_amount = worker_amount[1]

    if form['new_title']:
        work_type.name = form['new_title']

    try:
        work_type.save()
    except ValueError:
        return JsonResponse.value_error('Error upon saving work type instance. One of the parameters is invalid')

    front_operations = json.loads(form['operation_types'])
    if front_operations:  # todo: aa: is else must exist? each worktype must have 1+ operation
        existing_operation_types = {
            x.id: x for x in OperationType.objects.filter(work_type=work_type, dttm_deleted__isnull=True)
        }

        if len(front_operations) == 1 and len(existing_operation_types.keys()) == 1:  # была 1 , стала 1 => та же самая
            operation_type = list(existing_operation_types.values())[0]
            operation_type.name = front_operations[0]['name']
            operation_type.speed_coef = front_operations[0]['speed_coef']
            operation_type.do_forecast = front_operations[0]['do_forecast']
            try:
                # todo: aa: add check of params in form
                operation_type.save()
            except ValueError:
                return JsonResponse.value_error(err_operation)
            existing_operation_types = dict()

        else:
            for oper_dict in front_operations:
                if 'id' in oper_dict.keys() and oper_dict['id'] in existing_operation_types.keys():
                    ot = existing_operation_types[oper_dict['id']]
                    ot.name = oper_dict['name']
                    ot.speed_coef = oper_dict['speed_coef']
                    ot.do_forecast = oper_dict['do_forecast']
                    try:
                        # todo: aa: add check of params in form
                        ot.save()
                    except ValueError:
                        return JsonResponse.value_error(err_operation)
                    existing_operation_types.pop(oper_dict['id'])
                else:
                    try:
                        # todo: aa: add check of params in form
                        OperationType.objects.create(
                            work_type_id=work_type_id,
                            name=oper_dict['name'],
                            speed_coef=oper_dict['speed_coef'],
                            do_forecast=oper_dict['do_forecast'],
                        )
                    except (TypeError, IntegrityError) as e:
                        return JsonResponse.internal_error(err_operation)

        OperationType.objects.filter(id__in=existing_operation_types.keys()).update(
            dttm_deleted=datetime.datetime.now()
        )

    front_slots = json.loads(form['slots'])
    existing_slots = {
        x.id: x for x in Slot.objects.filter(work_type=work_type, dttm_deleted__isnull=True)
    }

    for slot_dict in front_slots:
        if 'id' in slot_dict.keys() and slot_dict['id'] in existing_slots.keys():
            existing_slot = existing_slots[slot_dict['id']]
            existing_slot.name = slot_dict['name']
            existing_slot.tm_start = slot_dict['tm_start']
            existing_slot.tm_end = slot_dict['tm_end']
            try:
                existing_slot.save()  # todo: aa: add check of params in form
                existing_slots.pop(slot_dict['id'])
            except Exception:
                return JsonResponse.internal_error(err_slot)
        else:
            # todo: aa: fields in slot_dict not checked!!!
            slot_dict.update({
                'work_type_id': work_type_id,
                'shop_id': shop_id
            })
            try:
                Slot.objects.create(**slot_dict)
            except Exception:
                return JsonResponse.internal_error(err_slot)
    # удаляем старые слоты
    Slot.objects.filter(id__in=existing_slots.keys()).update(dttm_deleted=datetime.datetime.now())

    return JsonResponse.success({
        'active_operation_types': [
            OperationTypeConverter.convert(ot) for ot in OperationType.objects.filter(
                work_type_id=work_type_id, dttm_deleted__isnull=True
            )
        ]
    })

