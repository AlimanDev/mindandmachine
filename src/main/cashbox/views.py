import datetime

from src.db.models import CashboxType, Cashbox, User, Shop
from src.util.db import CashboxTypeUtil
from src.util.forms import FormUtil
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import CashboxTypeConverter, CashboxConverter
from .forms import GetTypesForm, GetCashboxesForm, CreateCashboxForm, DeleteCashboxForm, UpdateCashboxForm
from src.main.other.notification.utils import send_notification


@api_method('GET', GetTypesForm, groups=User.__all_groups__)
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
                | 'id': cashbox_type_id,
                | 'dttm_deleted': дата удаления(здесь везде null),
                | 'shop': shop_id,
                | 'is_stable': True/False,
                | 'dttm_added': дата добавления,
                | 'speed_coef': int,
                | 'name': имя типа
            },...
        ]
    """
    shop_id = FormUtil.get_shop_id(request, form)

    # todo: add selecting in time period
    types = CashboxType.objects.filter(
        shop_id=shop_id,
        dttm_deleted__isnull=True,
    )

    return JsonResponse.success(
        [CashboxTypeConverter.convert(x) for x in CashboxTypeUtil.sort(types)]
    )


@api_method('GET', GetCashboxesForm, groups=User.__all_groups__)
def get_cashboxes(request, form):
    """
    Возвращает список касс для заданных в cashbox_types_ids типов

    Args:
        method: GET
        url: api/cashbox/get_cashboxes
        shop_id(int): required = False
        from_dt(QOS_DATE): required = False
        to_dt(QOS_DATE): required = False
        cashbox_type_ids(list): список типов касс

    Returns:
        {
            'cashbox_types':{
                cashbox_type_id: {
                    | 'dttm_deleted': дата-время удаления (null),
                    | 'dttm_added': дата-время добавления,
                    | 'shop': shop_id,
                    | 'id': id типа кассы,
                    | 'is_stable': True/False,
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
    shop_id = FormUtil.get_shop_id(request, form)
    dt_from = FormUtil.get_dt_from(form)
    dt_to = FormUtil.get_dt_to(form)
    cashbox_type_ids = form['cashbox_type_ids']

    cashboxes = Cashbox.objects.select_related(
        'type'
    ).filter(
        type__shop_id=shop_id,
    )

    types = CashboxTypeUtil.fetch_from_cashboxes(cashboxes)

    if len(cashbox_type_ids) > 0:
        cashboxes = [x for x in cashboxes if x.type_id in cashbox_type_ids]

    cashboxes = [x for x in cashboxes if dt_from <= x.dttm_added.date() <= dt_to or dt_from <= x.dttm_deleted.date() <= dt_to]

    return JsonResponse.success({
        'cashboxes_types': {x.id: CashboxTypeConverter.convert(x) for x in CashboxTypeUtil.sort(types)},
        'cashboxes': [CashboxConverter.convert(x) for x in cashboxes]
    })


@api_method(
    'POST',
    CreateCashboxForm,
    lambda_func=lambda x: CashboxType.objects.get(id=x['cashbox_type_id']).shop
)
def create_cashbox(request, form):
    """
    Создает новую кассу

    Args:
        method: POST
        url: /api/cashbox/create_cashbox
        cashbox_type_id(int): id типа кассы, к которой будет привязана созданная касса
        number(str): номер кассы

    Returns:
        {
            'cashbox_type': {
                | 'id': id типа кассы,
                | 'dttm_added': ,
                | 'dttm_deleted': ,
                | 'shop': shop_id,
                | 'name': название типа кассы,
                | 'is_stable': True/False,
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
    cashbox_type_id = form['cashbox_type_id']
    cashbox_number = form['number']

    try:
        cashbox_type = CashboxType.objects.get(id=cashbox_type_id)
    except CashboxType.DoesNotExist:
        return JsonResponse.does_not_exists_error('cashbox_type does not exist')

    cashboxes_count = Cashbox.objects.select_related(
        'type'
    ).filter(
        type__shop_id=cashbox_type.shop_id,
        dttm_deleted=None,
        number=cashbox_number
    ).count()

    if cashboxes_count > 0:
        return JsonResponse.already_exists_error('Cashbox with number already exists')

    cashbox = Cashbox.objects.create(type=cashbox_type, number=cashbox_number)

    send_notification('C', cashbox, sender=request.user)

    return JsonResponse.success({
        'cashbox_type': CashboxTypeConverter.convert(cashbox_type),
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
    shop_id = FormUtil.get_shop_id(request, form)

    try:
        cashbox = Cashbox.objects.select_related(
            'type'
        ).get(
            type__shop_id=shop_id,
            dttm_deleted=None,
            number=form['number']
        )
    except Cashbox.DoesNotExist:
        return JsonResponse.does_not_exists_error()
    except Cashbox.MultipleObjectsReturned:
        return JsonResponse.internal_error()

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
    lambda_func=lambda x: CashboxType.objects.get(id=x['to_cashbox_type_id'].shop)
)
def update_cashbox(request, form):
    """
    Меняет тип кассы у кассы с заданным номером

    Args:
        method: POST
        url: /api/cashbox/update_cashbox
        from_cashbox_type_id(int): с какого типа меняем
        to_cashbox_type_id(int): на какой
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
        JsonResponse.does_not_exists_error: если тип кассы с from/to_cashbox_type_id не существует\
        или если кассы с заданным номером и привязанной к данному типу не существует
        JsonResponse.multiple_objects_returned: если вернулось несколько объектов в QuerySet'e

    """
    cashbox_number = form['number']

    try:
        from_cashbox_type = CashboxType.objects.get(id=form['from_cashbox_type_id'])
    except CashboxType.DoesNotExist:
        return JsonResponse.does_not_exists_error('from_cashbox_type')

    try:
        to_cashbox_type = CashboxType.objects.get(id=form['to_cashbox_type_id'])
    except CashboxType.DoesNotExist:
        return JsonResponse.does_not_exists_error('to_cashbox_type')

    try:
        cashbox = Cashbox.objects.select_related(
            'type'
        ).filter(
            type__shop_id=from_cashbox_type.shop_id,
            dttm_deleted=None,
            number=cashbox_number
        )
    except Cashbox.DoesNotExist:
        return JsonResponse.does_not_exists_error('cashbox')
    except Cashbox.MultipleObjectsReturned:
        return JsonResponse.multiple_objects_returned()

    cashbox.dttm_deleted = datetime.datetime.now()
    cashbox.save()

    cashbox = Cashbox.objects.create(type=to_cashbox_type, number=cashbox_number)

    return JsonResponse.success(
        CashboxConverter.convert(cashbox)
    )
