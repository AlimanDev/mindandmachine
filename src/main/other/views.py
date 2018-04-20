from src.db.models import Shop, SuperShop, User
from src.util.forms import FormUtil
from src.util.models_converter import ShopConverter, SuperShopConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetDepartmentForm, GetSuperShopForm, GetSuperShopListForm


@api_method('GET', GetDepartmentForm)
def get_department(request, form):
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


@api_method('GET', GetSuperShopForm)
def get_super_shop(request, form):
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


@api_method('GET', GetSuperShopListForm)
def get_super_shop_list(request, form):
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
