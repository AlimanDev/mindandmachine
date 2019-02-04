from src.db.models import (
    Shop,
    SuperShop,
    User,
    Region,
    Timetable,
)
from math import ceil
from src.util.utils import api_method, JsonResponse
import datetime
from dateutil.relativedelta import relativedelta
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
    AddSuperShopForm,
    EditSuperShopForm,
    GetParametersForm,
    SetParametersForm,
    GetSuperShopStatsForm,
)


@api_method('GET', GetDepartmentForm)
def get_department(request, form):
    """
    Возвращает информацию об отделе

    Args:
        method: GET
        url: api/shop/get_department
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
        url: api/shop/get_super_shop
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

    return_list = []
    dynamic_values = dict(
        revenue_fot=dict(prev=1, curr=1, change=-17),
        fot=dict(prev=1, curr=1, change=13),
        idle=dict(prev=1, curr=1, change=-1),
        lack=dict(prev=1, curr=1, change=40),
        workers=dict(prev=20, curr=30, change=10)
    )
    for shop in shops:
        converted = ShopConverter.convert(shop)
        converted.update(dynamic_values)
        return_list.append(converted)

    return JsonResponse.success({
        'shops': return_list,
        'super_shop': SuperShopConverter.convert(super_shop)
    })


@api_method(
    'GET',
    GetSuperShopListForm,
    groups=[User.GROUP_HQ],
    lambda_func=lambda x: False
)
def get_super_shop_list(request, form):
    """
    Возвращает список магазинов, которые подходят под параметры (см. args)

    Args:
        method: GET
        url: api/shop/get_super_shop_list
        pointer(int): указывает с айдишника какого магазина в querysete всех магазов будем инфу отдавать
        items_per_page(int): сколько шопов будем на фронте показывать
        title(str): required = False, название магазина
        super_shop_type(['H', 'C']): type of supershop
        region(str): title of region
        closed_before_dt(QOS_DATE): closed before this date
        opened_after_dt(QOS_DATE): opened after this date
        revenue_fot(str): range in format '123-345'
        revenue(str): range
        lack(str): range, percents
        fot(str): range
        idle(str): range, percents
        workers_amount(str): range
        sort_type(str): по какому параметру сортируем
    Returns:
        {
            'super_shops': [список магазинов],
            'amount': количество магазинов
        }
    """
    pointer = form['pointer']
    amount = form['items_per_page']
    sort_type = form['sort_type']
    filter_dict = {
        'title__icontains': form['title'],
        'type': form['super_shop_type'],
        'region__title': form['region'],
        'dt_opened__gte': form['opened_after_dt'],
        'dt_closed__lte': form['closed_before_dt']
    }
    filter_dict = {k: v for k, v in filter_dict.items() if v}

    super_shops = SuperShop.objects.select_related('region').filter(**filter_dict)
    if sort_type:
        # todo: make work
        super_shops.order_by(sort_type)
    total = super_shops.count()
    super_shops = super_shops[amount*pointer:amount*(pointer + 1)]
    return_list = []
    dynamic_values = dict(
        revenue_fot=dict(prev=1, curr=1, change=-17),
        fot=dict(prev=1, curr=1, change=13),
        idle=dict(prev=1, curr=1, change=-1),
        lack=dict(prev=1, curr=1, change=40),
        workers=dict(prev=1, curr=1, change=40),
    )
    for ss in super_shops:
        # НЕ ТРОГАТЬ. работает только так
        converted_ss = SuperShopConverter.convert(ss)
        converted_ss.update(dynamic_values)

        return_list.append(converted_ss)

    return JsonResponse.success({
        'pages': ceil(total / amount),
        'shops': return_list
    })


@api_method(
    'POST',
    AddSuperShopForm,
    groups=[User.GROUP_HQ],
    lambda_func=lambda x: False
)
def add_supershop(request, form):
    try:
        region = Region.objects.get(title=form['region'])
    except Region.DoesNotExist:
        region = None
    try:
        SuperShop.objects.create(
            title=form['title'],
            code=form['code'],
            address=form['address'],
            dt_opened=form['open_dt'],
            region=region,
            tm_start=form['tm_start'],
            tm_end=form['tm_end']
        )
    except Exception as exc:
        return JsonResponse.internal_error('Error while creating shop: {}'.format(str(exc)))
    return JsonResponse.success()


@api_method(
    'POST',
    EditSuperShopForm,
    groups=[User.GROUP_HQ],
    lambda_func=lambda x: False
)
def edit_supershop(request, form):
    try:
        ss = SuperShop.objects.get(id=form['supershop_id'])
    except SuperShop.DoesNotExist:
        return JsonResponse.internal_error('No such supershop')

    ss.title = form['title']
    ss.code = form['code']
    ss.address = form['address']
    ss.dt_closed = form['close_dt']
    try:
        region = Region.objects.get(title=form['region'])
    except Region.DoesNotExist:
        return JsonResponse.internal_error('No such region')
    ss.region = region
    ss.tm_start = form['tm_start']
    ss.tm_end = form['tm_end']
    ss.save()

    return JsonResponse.success(SuperShopConverter.convert(ss))


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
            | absenteeism: int,
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
        'absenteeism': shop.absenteeism,
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
    shop.absenteeism = form['absenteeism']
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


@api_method(
    'GET',
    GetSuperShopStatsForm,
    groups=[User.GROUP_HQ],
    lambda_func=lambda x: False
)
def get_supershop_stats(request, form):
    try:
        super_shop = SuperShop.objects.get(id=form['supershop_id'])
    except SuperShop.DoesNotExist:
        return JsonResponse.internal_error('No such SuperShop in database')
    shops = Shop.objects.select_related('super_shop').filter(super_shop=super_shop)
    dt_now = datetime.date.today()
    dt_from = dt_now - relativedelta(months=6)

    successful_tts = Timetable.objects.select_related('shop').filter(
        dt=(dt_now + relativedelta(months=1)).replace(day=1),
        shop_id__in=shops.values_list('id', flat=True),
        status=Timetable.Status.READY.value,
    ).count()

    fot_revenue_stats = []

    import random
    while dt_from <= dt_now:
        fot_revenue_stats.append({
            'dt': BaseConverter.convert_date(dt_from),
            'value': random.randint(40, 60)
        })
        dt_from += relativedelta(days=1)

    return JsonResponse.success({
        'shop_tts': '{}/{}'.format(successful_tts, shops.count()),
        'fot_revenue': fot_revenue_stats,
        'stats': {
            'curr': {
                'fot_revenue': random.randint(40, 60),
                'idle': random.randint(40, 60),
                'lack': random.randint(40, 60),
                'revenue': random.randint(1000000, 2000000),
                'workers': random.randint(100, 120)
            },
            'next': {} if not successful_tts else {
                'fot_revenue': random.randint(40, 60),
                'idle': random.randint(40, 60),
                'lack': random.randint(40, 60),
                'revenue': random.randint(1000000, 2000000),
                'revenue_growth': random.randint(10, 20),
                'workers': random.randint(100, 120)
            }
        }
    })