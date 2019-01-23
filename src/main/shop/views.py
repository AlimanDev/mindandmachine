from src.db.models import (
    Shop,
    SuperShop,
    User,
)
from src.util.utils import api_method, JsonResponse
from src.util.forms import FormUtil
from src.util.models_converter import (
    ShopConverter,
    SuperShopConverter,
    BaseConverter,
)
from .forms import (
    GetDepartmentForm,
    GetSuperShopForm,
    GetSuperShopListForm,
    GetParametersForm,
    SetParametersForm,
)


@api_method('GET', GetDepartmentForm)
def get_department(request, form):
    """
    Возвращает информацию об отделе

    Args:
        method: GET
        url: api/other/get_department
        shop_id(int): required=False

    Returns:
        {
            'shop': {
                | 'id': id отдела,
                | 'super_shop': id магазина,
                | 'full_interface'(bool): ,
                | 'title': название отдела
            | },
            | 'shops': [Список отделов, которые есть в этом магазине в таком формате как выше],
            'super_shop':{
                | 'id': id магазина,
                | 'title': название магазина,
                | 'code': код магазина,
                | 'dt_opened': дата открытия,
                | 'dt_closed': дата закрытия (null)
            }
        }

    """
    shop_id = FormUtil.get_shop_id(request, form)

    try:
        shop = Shop.objects.select_related('super_shop').get(id=shop_id)
    except:
        return JsonResponse.does_not_exists_error('shop')

    all_shops = Shop.objects.filter(super_shop_id=shop.super_shop_id)

    return JsonResponse.success({
        'shop': ShopConverter.convert(shop),
        'all_shops': [ShopConverter.convert(x) for x in all_shops],
        'super_shop': SuperShopConverter.convert(shop.super_shop)
    })


@api_method('GET', GetSuperShopForm, check_permissions=False)
def get_super_shop(request, form):
    """
    Возвращает информацию о магазине

    Args:
        method: GET
        url: api/other/get_super_shop
        super_shop_id(int): required=True

    Returns:
         {
            'shops': [список магазинов в формате как выше],\n
            'super_shop':{
                | 'id': id магазина,
                | 'title': название магазина,
                | 'code': код магазина,
                | 'dt_opened': дата открытия,
                | 'dt_closed': дата закрытия (null)
            }
         }
    """
    super_shop_id = form['super_shop_id']

    try:
        super_shop = SuperShop.objects.get(id=super_shop_id)
    except SuperShop.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    shops = Shop.objects.filter(super_shop=super_shop)

    return JsonResponse.success({
        'shops': [ShopConverter.convert(x) for x in shops],
        'super_shop': SuperShopConverter.convert(super_shop)
    })


@api_method('GET', GetSuperShopListForm, check_permissions=False)
def get_super_shop_list(request, form):
    """
    Возвращает список магазинов, которые подходят под параметры (см. args)

    Args:
        method: GET
        url: api/other/get_super_shop_list
        closed_after_dt(QOS_DATE):
        closed_before_dt(QOS_DATE):
        min_worker_amount(int): required = False
        max_worker_amount(int): required = False

    Returns:
        {
            'super_shops': [список магазинов],
            'amount': количество магазинов
        }
    """
    shops = Shop.objects.select_related('super_shop').all()
    super_shops = {}
    for x in shops:
        super_shops.setdefault(x.super_shop_id, x.super_shop)

    dt = form.get('closed_after_dt')
    if dt is not None:
        super_shops = {k: v for k, v in super_shops.items() if v.dt_closed is None or v.dt_closed > dt}

    dt = form.get('opened_before_dt')
    if dt is not None:
        super_shops = {k: v for k, v in super_shops.items() if v.dt_opened is None or v.dt_opened < dt}

    min_worker_amount = form.get('min_worker_amount')
    max_worker_amount = form.get('max_worker_amount')

    if min_worker_amount is not None or max_worker_amount is not None:
        worker_amount = {k: User.objects.select_related('shop').filter(shop__super_shop_id=k).count() for k in super_shops}

        if min_worker_amount is not None:
            super_shops = {k: v for k, v in super_shops.items() if worker_amount[k] >= min_worker_amount}

        if max_worker_amount is not None:
            super_shops = {k: v for k, v in super_shops.items() if worker_amount[k] <= max_worker_amount}

    return JsonResponse.success({
        'super_shops': [SuperShopConverter.convert(x) for x in super_shops.values()],
        'amount': len(super_shops)
    })


@api_method(
    'GET',
    GetParametersForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def get_parameters(request, form):
    """
    Возвращает параметры для указанного магазина

    Args:
        method: GET
        url: /api/shop/get_parameters
        shop_id(int): required = False

    Returns:
        {
            | queue_length: int,
            | idle: int,
            | fot: int,
            | less_norm: int(0-100),
            | more_norm: int(0-100),
            | tm_shop_opens: Str,
            | tm_shop_closes: Str,
            | restricted_start_times: [
                '10:00', '12:00', '14:00', '10:00', '12:00', '14:00',
                '10:00', '12:00', '14:00', '10:00', '12:00'
            ],
            | restricted_end_times: [
                '10:00', '12:00', '14:00'
            ],
            | min_change_time: int,
            | even_shift_morning_evening: Boolean,
            | paired_weekday: Boolean,
            | exit1day: Boolean,
            | exit42hours: Boolean,
            | process_type: 'N'/'P' (N -- po norme, P -- po proizvodst)
        }
    """
    shop = Shop.objects.get(id=FormUtil.get_shop_id(request, form))

    return JsonResponse.success({
        'queue_length': shop.mean_queue_length,
        'idle': shop.idle,
        'fot': shop.fot,
        'less_norm': shop.less_norm,
        'more_norm': shop.more_norm,
        'tm_shop_opens': BaseConverter.convert_time(shop.tm_shop_opens),
        'tm_shop_closes': BaseConverter.convert_time(shop.tm_shop_closes),
        'shift_start': shop.shift_start,
        'shift_end': shop.shift_end,
        'restricted_start_times': shop.restricted_start_times,
        'restricted_end_times': shop.restricted_end_times,
        'min_change_time': shop.min_change_time,
        'even_shift': shop.even_shift_morning_evening,
        'paired_weekday': shop.paired_weekday,
        'exit1day': shop.exit1day,
        'exit42hours': shop.exit42hours,
        'process_type': shop.process_type,
    })


@api_method(
    'POST',
    SetParametersForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def set_parameters(request, form):
    """
        Задает параметры для магазина

        Args:
            method: POST
            url: /api/shop/set_parameters
            shop_id(int): required = False
            + все те же что и в get_parameters

    """
    shop = Shop.objects.get(id=FormUtil.get_shop_id(request, form))

    shop.mean_queue_length = form['queue_length']
    shop.idle = form['idle']
    shop.fot = form['fot']
    shop.less_norm = form['less_norm']
    shop.more_norm = form['more_norm']
    shop.tm_shop_opens = form['tm_shop_opens']
    shop.tm_shop_closes = form['tm_shop_closes']
    shop.shift_start = form['shift_start']
    shop.shift_end = form['shift_end']
    shop.restricted_start_times = form['restricted_start_times']
    shop.restricted_end_times = form['restricted_end_times']
    shop.min_change_time = form['min_change_time']
    shop.even_shift_morning_evening = form['even_shift_morning_evening']
    shop.paired_weekday = form['paired_weekday']
    shop.exit1day = form['exit1day']
    shop.exit42hours = form['exit42hours']
    shop.process_type = form['process_type']

    try:
        shop.save()
    except:
        return JsonResponse.internal_error('Один из параметров задан неверно.')

    return JsonResponse.success()
