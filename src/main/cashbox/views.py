import datetime

from src.db.models import CashboxType, Cashbox, User, Shop, WorkerDayCashboxDetails
from src.util.db import CashboxTypeUtil
from src.util.forms import FormUtil
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import CashboxTypeConverter, CashboxConverter
from .forms import (
    GetTypesForm,
    GetCashboxesForm,
    CreateCashboxForm,
    DeleteCashboxForm,
    UpdateCashboxForm,
    CreateCashboxTypeForm,
    DeleteCashboxTypeForm,
    CashboxesOpenTime,
    CashboxesUsedResource,
)

from src.main.tablet.utils import time_diff
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

    cashboxes = [x for x in cashboxes if
                 dt_from <= x.dttm_added.date() <= dt_to or dt_from <= x.dttm_deleted.date() <= dt_to]

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


@api_method('POST', CreateCashboxTypeForm)
def create_cashbox_type(request, form):
    """
    Создает тип касс с заданным именем

    Args:
        method: POST
        url: /api/cashbox/create_cashbox_type
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
            | 'is_stable': True,
            | 'speed_coef': 1
        }

    Raises:
        JsonResponse.already_exists_error: если тип касс с таким именем уже существует
    """
    shop_id = FormUtil.get_shop_id(request, form)
    name = form['name']

    if CashboxType.objects.filter(name=name, shop_id=shop_id, dttm_deleted__isnull=True).count() > 0:
        return JsonResponse.already_exists_error('cashbox type already exists')

    new_cashbox_type = CashboxType.objects.create(
        name=name,
        shop_id=shop_id,
        is_main_type=True if name == 'Линия' else False
    )

    send_notification('C', new_cashbox_type, sender=request.user)

    return JsonResponse.success(CashboxTypeConverter.convert(new_cashbox_type))


@api_method(
    'POST',
    DeleteCashboxTypeForm,
    lambda_func=lambda x: CashboxType.objects.get(id=x['cashbox_type_id']).shop
)
def delete_cashbox_type(request, form):
    """
    Удаляет тип касс с заданным id'шником

    Args:
        method: POST
        url: /api/cashbox/delete_cashbox_type
        cashbox_type_id(int): required = True

    Note:
        Также отправлет уведомление о том, что тип касс был удален

    Returns:
        {
            | 'id': id новой созданной кассы,
            | 'dttm_added': дата добавления,
            | 'dttm_deleted': дата удаления(сейчас),
            | 'shop': id shop'a,
            | 'name': имя,
            | 'is_stable': True/False,
            | 'speed_coef': int
        }

    Raises:
        JsonResponse.internal_error: если к данному типу касс привязаны какие-то кассы
    """
    cashbox_type = CashboxType.objects.get(id=form['cashbox_type_id'])

    attached_cashboxes = Cashbox.objects.filter(type=cashbox_type, dttm_deleted__isnull=True)

    if attached_cashboxes.count() > 0:
        return JsonResponse.internal_error('there are cashboxes on this type')

    cashbox_type.dttm_deleted = datetime.datetime.now()
    cashbox_type.save()

    send_notification('D', cashbox_type, sender=request.user)

    return JsonResponse.success(CashboxTypeConverter.convert(cashbox_type))


@api_method('GET', CashboxesOpenTime)
def get_cashboxes_open_time(request, form):
    """
    Возвращает процент "используемости" касс по отношению к периоду

    Args:
        method: GET
        url: /api/cashbox/get_cashboxes_open_time
        shop_id(int): required = False
        from_dt(QOS_DATE): с какого периода
        to_dt(QOS_DATE): по какой период

    Returns:
        {
            cashbox_id: {
                'share_time': float
            },..
        }

    """
    response = {}
    shop_id = FormUtil.get_shop_id(request, form)
    dt_from = FormUtil.get_dt_from(form)
    dt_to = FormUtil.get_dt_to(form)

    def update_response(last_cashbox_id, share_of_open_time, duration_of_the_shop):
        percent = round(share_of_open_time * 100 / duration_of_the_shop, 3)
        response[last_cashbox_id] = {
            'share_time': percent if percent < 100 else 100
        }

    cashboxes = Cashbox.objects.qos_filter_active(
        dt_from,
        dt_to,
        type__shop=shop_id
    )
    for cashbox in cashboxes:
        response[cashbox.id] = {
            'share_time': 0
        }

    worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related(
        'cashbox_type__shop',
        'worker_day',
    ).filter(
        status=WorkerDayCashboxDetails.TYPE_WORK,
        cashbox_type__shop=shop_id,
        on_cashbox__isnull=False,
        worker_day__dt__gte=dt_from,
        worker_day__dt__lte=dt_to,
        dttm_to__isnull=False,
        is_tablet=True,
    ).order_by('on_cashbox')

    if len(worker_day_cashbox_details):
        share_of_open_time = 0
        last_cashbox = worker_day_cashbox_details[0].on_cashbox
        duration_of_the_shop = time_diff(worker_day_cashbox_details[0].cashbox_type.shop.super_shop.tm_start,
                                         worker_day_cashbox_details[0].cashbox_type.shop.super_shop.tm_end) * (
                                       (dt_to - dt_from).days + 1)

        for detail in worker_day_cashbox_details:
            if detail.on_cashbox == last_cashbox:
                share_of_open_time += (detail.dttm_to - detail.dttm_from).total_seconds()
            else:
                update_response(last_cashbox.id, share_of_open_time, duration_of_the_shop)
                last_cashbox = detail.on_cashbox
                share_of_open_time = (detail.dttm_to - detail.dttm_from).total_seconds()

        update_response(last_cashbox.id, share_of_open_time, duration_of_the_shop)

    return JsonResponse.success(response)


@api_method('GET', CashboxesUsedResource)
def get_cashboxes_used_resource(request, form):
    """
    Возвращает доли времени для разных перегрузок типов касс в зависимости от выбранного периода работы

    Args:
        method: GET
        url: /api/cashbox/get_cashboxes_used_resource
        shop_id(int): required = False
        from_dt(QOS_DATE): с какого периода
        to_dt(QOS_DATE): по какой период

    Returns:
        {
            cashbox_type_id : {
                | '20': int,
                | '40': int,
                | '60': int,
                | '80': int,
                | '100': int
            },...
        }
    """

    def get_percent(response, cashbox_type_id, current_dttm, worker_day_cashbox_details, count_of_cashbox):
        count = 0
        for detail in worker_day_cashbox_details:
            if current_dttm < detail.dttm_from:
                break

            if detail.dttm_from <= current_dttm <= detail.dttm_to:
                count += 1

            if detail.dttm_to < current_dttm <= detail.dttm_to:
                worker_day_cashbox_details.remove(detail)

        percent = count / count_of_cashbox * 100 if count_of_cashbox > 0 else 0
        if 0 < percent <= 20:
            response[cashbox_type_id]['20'] += 1
        elif 20 < percent <= 40:
            response[cashbox_type_id]['40'] += 1
        elif 40 < percent <= 60:
            response[cashbox_type_id]['60'] += 1
        elif 60 < percent <= 80:
            response[cashbox_type_id]['80'] += 1
        elif 80 < percent <= 100:
            response[cashbox_type_id]['100'] += 1
        else:
            pass
    response = {}
    shop_id = FormUtil.get_shop_id(request, form)
    dt_from = FormUtil.get_dt_from(form)
    dt_to = FormUtil.get_dt_to(form)
    time_delta = 300

    cashbox_types = CashboxType.objects.qos_filter_active(
        dttm_from=datetime.datetime.combine(dt_from, datetime.time(23, 59, 59)),
        dttm_to=datetime.datetime.combine(dt_to, datetime.time(0, 0, 0)),
        shop=shop_id,
    )
    super_shop = cashbox_types[0].shop.super_shop if len(cashbox_types) else None

    duration_of_the_shop = time_diff(super_shop.tm_start, super_shop.tm_end) * ((dt_to - dt_from).days + 1) \
        if super_shop else None

    if duration_of_the_shop:

        start_time = datetime.datetime.combine(dt_from, super_shop.tm_start)

        for cashbox_type in cashbox_types:
            current_dttm = start_time
            count_of_cashbox = Cashbox.objects.filter(type=cashbox_type).count()
            response[cashbox_type.id] = {
                '20': 0,
                '40': 0,
                '60': 0,
                '80': 0,
                '100': 0
            }

            worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
                status=WorkerDayCashboxDetails.TYPE_WORK,
                cashbox_type=cashbox_type,
                is_tablet=True,
                on_cashbox__isnull=False,
                worker_day__dt__gte=dt_from,
                worker_day__dt__lte=dt_to,
                dttm_to__isnull=False,
            ).order_by('on_cashbox', 'worker_day__dt', 'dttm_from')

            if worker_day_cashbox_details:
                details = list(worker_day_cashbox_details)
                while current_dttm.date() <= dt_to:
                    get_percent(response, cashbox_type.id, current_dttm, details, count_of_cashbox)
                    current_dttm += datetime.timedelta(seconds=time_delta)

                for range_percentages in response[cashbox_type.id]:
                    response[cashbox_type.id][range_percentages] = round(response[cashbox_type.id][range_percentages] /
                                                                         (duration_of_the_shop / time_delta / 100), 3)

    return JsonResponse.success(response)

