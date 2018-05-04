from src.db.models import Shop, SuperShop, User, Notifications
from src.util.forms import FormUtil
from src.util.models_converter import ShopConverter, SuperShopConverter, NotificationConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetDepartmentForm, GetSuperShopForm, GetSuperShopListForm, GetNotificationsForm, GetNewNotificationsForm, SetNotificationsReadForm


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


@api_method('GET', GetNotificationsForm)
def get_notifications(request, form):
    pointer = form.get('pointer')
    count = form['count']

    user = request.user

    notifications = Notifications.objects.filter(to_worker=user).order_by('-id')
    if pointer is not None:
        notifications = notifications.filter(id__lt=pointer)
    notifications = list(notifications[:count])

    result = {
        'get_noty_pointer': notifications[-1].id if len(notifications) > 0 else None,
        'noty': [NotificationConverter.convert(x) for x in notifications]
    }

    if pointer is None:
        result['get_new_noty_pointer'] = notifications[0].id if len(notifications) > 0 else -1
        result['unread_count'] = Notifications.objects.filter(to_worker=user, was_read=False).count()

    return JsonResponse.success(result)


@api_method('GET', GetNewNotificationsForm)
def get_new_notifications(request, form):
    pointer = form['pointer']
    count = form['count']

    user = request.user

    notifications = [x for x in reversed(Notifications.objects.filter(to_worker=user, id__gt=pointer).order_by('id')[:count])]
    unread_count = Notifications.objects.filter(to_worker=user, was_read=False).count()

    return JsonResponse.success({
        'get_new_noty_pointer': notifications[0].id if len(notifications) > 0 else pointer,
        'noty': [NotificationConverter.convert(x) for x in notifications],
        'unread_count': unread_count
    })


@api_method('POST', SetNotificationsReadForm)
def set_notifications_read(request, form):
    count = Notifications.objects.filter(user=request.user, id__in=form['ids']).update(was_read=True)
    return JsonResponse.success({
        'updated_count': count
    })
