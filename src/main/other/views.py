from src.db.models import (
    Shop,
    SuperShop,
    User,
    Slot,
    UserWeekdaySlot,
)
from src.util.forms import FormUtil
from src.util.models_converter import ShopConverter, SuperShopConverter, BaseConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetDepartmentForm, GetSuperShopForm, GetSuperShopListForm, GetSlots, GetAllSlots, SetSlot
from collections import defaultdict
import datetime


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


@api_method('GET', GetAllSlots)
def get_all_slots(request, form):
    """
    Возвращает список слотов в магазине

    Args:
        method: GET
        url: api/other/get_all_slots
        shop_id(int): required = True

    Returns:
        {
            'slots': [
                {
                    | 'id': id слота,
                    | 'tm_start': время начала,
                    | 'tm_end': время конца,
                    | 'name': имя (может быть null)
                }, ...
            ]
        }

    """
    result = []
    slots = Slot.objects.filter(shop__id=form['shop_id'])
    for slot in slots:
        result.append({
            'id': slot.id,
            'name': slot.name,
            'tm_start': BaseConverter.convert_time(slot.tm_start),
            'tm_end': BaseConverter.convert_time(slot.tm_end),
        })
    return JsonResponse.success({
        'slots': result,
    })


@api_method('POST', SetSlot)
def set_slot(request, form):
    """

    Args:
        method: POST
        url: api/other/set_slot
        slots(str): список слотов (вроде)
        user_id(int):

    Returns:
        JsonResponse.success

    Raises:
        JsonResponse.value_error

    """
    # weekday = form['weekday']
    try:
        user = User.objects.get(id=form['user_id'])
    except User.DoesNotExist:
        return JsonResponse.does_not_exists_error('user_id')

    # slot = Slot.objects.get(id=form['slot_id'])
    shop_slots = Slot.objects.filter(shop_id=user.shop_id).values_list('id', flat=True)

    slots_list = []
    bad_slot = False
    for wd, slot_ids in form['slots'].items():
        for slot_id in slot_ids:
            if slot_id in shop_slots:
                slots_list.append(
                    UserWeekdaySlot(
                        worker=user,
                        weekday=wd,
                        slot_id=slot_id,
                    )
                )
            else:
                bad_slot =True
                break
        if bad_slot:
            break

    if not bad_slot:
        UserWeekdaySlot.objects.filter(worker=user).delete()
        UserWeekdaySlot.objects.bulk_create(slots_list)
        return JsonResponse.success()
    return JsonResponse.value_error('there is no slot with id {} in the shop (id {})'.format(slot_id, user.shop_id))


@api_method('GET', GetSlots)
def get_slots(request, form):
    """

    Args:
        method: GET
        url: api/other/get_slots
        user_id(int): required = True
        shop_id(int): required = False

    Returns:

    """
    weekday_slots = UserWeekdaySlot.objects.select_related(
        'slot'
    ).filter(
        worker_id=form['user_id']
    )

    slots_by_weekday = defaultdict(list)
    for ws in weekday_slots:
        slots_by_weekday[ws.weekday].append({
            'id': ws.slot.id,
            'name': ws.slot.name,
            'tm_start': BaseConverter.convert_time(ws.slot.tm_start),
            'tm_end': BaseConverter.convert_time(ws.slot.tm_end),
        })

    return JsonResponse.success({
        'slots': slots_by_weekday,
    })
