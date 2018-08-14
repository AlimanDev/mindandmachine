import datetime

from src.db.models import CashboxType, Cashbox, User, Shop, WorkerDayCashboxDetails
from src.util.db import CashboxTypeUtil
from src.util.forms import FormUtil
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import CashboxTypeConverter, CashboxConverter
from .forms import (GetTypesForm, GetCashboxesForm, CreateCashboxForm, DeleteCashboxForm, UpdateCashboxForm,
                    CashboxesOpenTime)


@api_method('GET', GetTypesForm, groups=User.__all_groups__)
def get_types(request, form):
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

    return JsonResponse.success({
        'cashbox_type': CashboxTypeConverter.convert(cashbox_type),
        'cashbox': CashboxConverter.convert(cashbox)
    })


@api_method(
    'GET',
    DeleteCashboxForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def delete_cashbox(request, form):
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

    return JsonResponse.success(
        CashboxConverter.convert(cashbox)
    )


@api_method(
    'POST',
    UpdateCashboxForm,
    lambda_func=lambda x: CashboxType.objects.get(id=x['to_cashbox_type_id'].shop)
)
def update_cashbox(request, form):
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
        return JsonResponse.internal_error()

    cashbox.dttm_deleted = datetime.datetime.now()
    cashbox.save()

    cashbox = Cashbox.objects.create(type=to_cashbox_type, number=cashbox_number)

    return JsonResponse.success(
        CashboxConverter.convert(cashbox)
    )


@api_method('GET', CashboxesOpenTime, groups=User.__all_groups__)
def get_cashboxes_open_time(request, form):
    from src.main.tablet.utils import time_diff
    response = {}
    shop_id = FormUtil.get_shop_id(request, form)
    dt_from = FormUtil.get_dt_from(form)
    dt_to = FormUtil.get_dt_to(form)
    shop = Shop.objects.select_related('super_shop').filter(
        id=shop_id,
    ).first()

    duration_of_the_shop = time_diff(shop.super_shop.tm_start, shop.super_shop.tm_end) * ((dt_to - dt_from).days + 1)
    print(shop.super_shop.tm_start, shop.super_shop.tm_end, duration_of_the_shop)

    worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related('cashbox_type', 'worker_day').filter(
        status=WorkerDayCashboxDetails.TYPE_WORK,
        cashbox_type__shop=shop,
        on_cashbox__isnull=False,
        # on_cashbox=14,
        worker_day__dt__gte=dt_from,
        worker_day__dt__lte=dt_to,
    ).order_by('on_cashbox')
    last_cashbox = worker_day_cashbox_details[0].on_cashbox if len(worker_day_cashbox_details) else None

    share_of_open_time = 0
    for detail in worker_day_cashbox_details:
        if detail.on_cashbox == last_cashbox:
            print('---------',share_of_open_time, duration_of_the_shop, detail.tm_from, detail.tm_to, detail.worker_day.worker_id, detail.worker_day.dt, detail.on_cashbox.id)

            if detail.tm_from and detail.tm_to:
                share_of_open_time += time_diff(detail.tm_from, detail.tm_to)
        else:
            response[last_cashbox.id] = {
                'share_time': share_of_open_time * 100 / duration_of_the_shop
            }
            last_cashbox = detail.on_cashbox
            share_of_open_time = 0

    if last_cashbox:
        response[last_cashbox.id] = {
            'share_time': share_of_open_time * 100 / duration_of_the_shop
        }

    return JsonResponse.success(response)
# http://127.0.0.1:8080/api/cashbox/get_cashboxes_open_time?shop_id=5&from_dt=02.5.2018&to_dt=4.5.2018
