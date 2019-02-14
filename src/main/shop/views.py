import datetime
from src.db.models import (
    Shop,
    SuperShop,
    User,
    Region,
    Timetable,
)
from math import ceil
from src.util.utils import api_method, JsonResponse
from .utils import (
    calculate_supershop_stats,
    get_super_shop_list_stats,
)
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
    EditShopForm,
    GetParametersForm,
    SetParametersForm,
    GetSuperShopStatsForm,
    AddShopForm,
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
    dt_now = datetime.date.today().replace(day=1)
    super_shop_id = form['super_shop_id']

    try:
        super_shop = SuperShop.objects.get(id=super_shop_id)
    except SuperShop.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    shops = Shop.objects.filter(super_shop=super_shop, dttm_deleted__isnull=True)

    return_list = []
    dynamic_values = dict()

    for shop in shops:
        shop_id = shop.id
        converted = ShopConverter.convert(shop)
        curr_stats = calculate_supershop_stats(dt_now, shop_id)
        prev_stats = calculate_supershop_stats(dt_now - relativedelta(months=1), shop_id)
        curr_stats.pop('revenue')
        prev_stats.pop('revenue')

        for key in curr_stats.keys():
            dynamic_values[key] = {
                'prev': prev_stats[key],
                'curr': curr_stats[key],
                'change': round((curr_stats[key] / prev_stats[key] - 1) * 100) if prev_stats[key] else 0
            }

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
        format(str): 'excel'/'raw'
    Returns:
        {
            'super_shops': [список магазинов],
            'amount': количество магазинов
        }
    """
    return_list, total = get_super_shop_list_stats(form)

    return JsonResponse.success({
        'pages': ceil(total / form['items_per_page']),
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

    SuperShop.objects.create(
        title=form['title'],
        code=form['code'],
        address=form['address'],
        dt_opened=form['open_dt'],
        region=region,
        tm_start=form['tm_start'],
        tm_end=form['tm_end']
    )
    return JsonResponse.success()


@api_method(
    'POST',
    AddShopForm,
    groups=[User.GROUP_HQ],
    lambda_func=lambda x: False
)
def add_shop(request, form):
    super_shop_id = form['super_shop_id']
    created = Shop.objects.create(
        title=form['title'],
        tm_shop_opens=form['tm_shop_opens'],
        tm_shop_closes=form['tm_shop_closes'],
        super_shop_id=super_shop_id
    )
    return JsonResponse.success(ShopConverter.convert(created))


@api_method(
    'POST',
    EditShopForm,
    groups=[User.GROUP_HQ],
    lambda_func=lambda x: False
)
def edit_shop(request, form):
    try:
        shop = Shop.objects.get(id=form['shop_id'])
    except Shop.DoesNotExist:
        return JsonResponse.internal_error('No such shop')

    if form['to_delete']:
        shop.dttm_deleted = datetime.datetime.now()
    else:
        shop.title = form['title']
        shop.tm_shop_opens = form['tm_shop_opens']
        shop.tm_shop_closes = form['tm_shop_closes']
    shop.save()

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
    if form['region']:
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
    shops = Shop.objects.filter(
        super_shop=super_shop,
        dttm_deleted__isnull=True
    )
    shop_ids = shops.values_list('id', flat=True)
    dt_now = datetime.date.today().replace(day=1)
    dt_from = dt_now - relativedelta(months=6)

    successful_tts = Timetable.objects.select_related('shop').filter(
        dt=dt_now + relativedelta(months=1),
        shop_id__in=shops.values_list('id', flat=True),
        status=Timetable.Status.READY.value,
    ).count()

    fot_revenue_stats = []

    while dt_from <= dt_now:
        fot_revenue_stats.append({
            'dt': BaseConverter.convert_date(dt_from),
            'value': calculate_supershop_stats(dt_from, shop_ids).pop('fot_revenue')
        })
        dt_from += relativedelta(months=1)

    curr_month_stats = calculate_supershop_stats(dt_now, shop_ids)
    curr_month_stats.pop('fot')
    next_month_stats = calculate_supershop_stats(dt_now + relativedelta(months=1), shop_ids)
    next_month_stats.pop('fot')
    if curr_month_stats['revenue']:
        revenue_growth = round(next_month_stats['revenue'] / curr_month_stats['revenue'] - 1, 2) * 100
    else:
        revenue_growth = -100
    next_month_stats.update({
        'revenue_growth': revenue_growth
    })

    return JsonResponse.success({
        'shop_tts': '{}/{}'.format(successful_tts, shops.count()),
        'fot_revenue': fot_revenue_stats,
        'stats': {
            'curr': curr_month_stats,
            'next': next_month_stats if successful_tts else {}
        }
    })