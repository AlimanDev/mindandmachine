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
    CashboxesOpenTime,
    CashboxesUsedResource
)

from src.main.tablet.utils import time_diff


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
    """
    Receiving the percentage of cashboxes working hours

    :param shop_id: id of the department
    :param dt_from: start date of the period
    :param dt_to: end date of the period

    :return: dictionary with a list of cashboxes and percentages of open time
    """

    response = {}
    shop_id = FormUtil.get_shop_id(request, form)
    dt_from = FormUtil.get_dt_from(form)
    dt_to = FormUtil.get_dt_to(form)

    cashboxes = Cashbox.objects.select_related('type__shop').filter(
        type__shop=shop_id
    )
    for cashbox in cashboxes:
        response[cashbox.id] = {
            'share_time': 0
        }

    worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related('cashbox_type__shop',
                                                                                'worker_day').filter(
        status=WorkerDayCashboxDetails.TYPE_WORK,
        cashbox_type__shop=shop_id,
        on_cashbox__isnull=False,
        worker_day__dt__gte=dt_from,
        worker_day__dt__lte=dt_to,
        tm_to__isnull=False,
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
                share_of_open_time += time_diff(detail.tm_from, detail.tm_to)
            else:
                percent = round(share_of_open_time * 100 / duration_of_the_shop, 3)
                response[last_cashbox.id] = {
                    'share_time': percent if percent < 100 else 100
                }
                last_cashbox = detail.on_cashbox
                share_of_open_time = time_diff(detail.tm_from, detail.tm_to)
        if last_cashbox:
            percent = round(share_of_open_time * 100 / duration_of_the_shop, 3)
            response[last_cashbox.id] = {
                'share_time': percent if percent < 100 else 100
            }
    return JsonResponse.success(response)


@api_method('GET', CashboxesUsedResource, groups=User.__all_groups__)
def get_cashboxes_used_resource(request, form):
    """
    Receipt of used cashboxes resource

    :param shop_id: id of the department
    :param dt_from: start date of the period
    :param dt_to: end date of the period

    :return: dictionary with a list of cashboxes and share of time
    """

    def get_percent(response, cashbox_type_id, current_dttm, worker_day_cashbox_details, count_of_cashbox):
        count = 0
        for detail in worker_day_cashbox_details:
            if detail.tm_from <= current_dttm.time() <= detail.tm_to and detail.worker_day.dt == current_dttm.date():
                count += 1

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

    cashbox_types = CashboxType.objects.filter(
        shop=shop_id,
    )
    super_shop = cashbox_types[0].shop.super_shop if len(cashbox_types) else None

    duration_of_the_shop = time_diff(super_shop.tm_start, super_shop.tm_end) * ((dt_to - dt_from).days + 1) \
        if super_shop else None

    start_time = datetime.datetime(year=dt_from.year, month=dt_from.month, day=dt_from.day,
                                   hour=super_shop.tm_start.hour, minute=super_shop.tm_start.minute,
                                   second=super_shop.tm_start.second)
    if duration_of_the_shop and start_time:

        for cashbox_type in cashbox_types:
            current_dttm = start_time
            count_of_cashbox = Cashbox.objects.filter(type=cashbox_type).count()
            response[cashbox_type.id] = {'20': 0,
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
                tm_to__isnull=False,
            ).order_by('on_cashbox', 'tm_from')

            if worker_day_cashbox_details:
                while current_dttm.date() <= dt_to:
                    get_percent(response, cashbox_type.id, current_dttm, worker_day_cashbox_details, count_of_cashbox)
                    current_dttm += datetime.timedelta(seconds=time_delta)

                for range_percentages in response[cashbox_type.id]:
                    response[cashbox_type.id][range_percentages] /= duration_of_the_shop / time_delta / 100

    return JsonResponse.success(response)
