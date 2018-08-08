import datetime

from src.db.models import CashboxType, Cashbox, User, Shop
from src.util.db import CashboxTypeUtil
from src.util.forms import FormUtil
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import CashboxTypeConverter, CashboxConverter
from .forms import GetTypesForm, GetCashboxesForm, CreateCashboxForm, DeleteCashboxForm, UpdateCashboxForm


@api_method(
    'GET',
    GetTypesForm,
    groups=User.__except_cashiers__,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
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


@api_method(
    'GET',
    GetCashboxesForm,
    groups=User.__except_cashiers__,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
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
    'POST',
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
