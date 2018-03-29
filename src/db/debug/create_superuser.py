from ..models import User, Shop


def create(username, email, password):
    shop_title = '_internal'
    try:
        shop = Shop.objects.get(title=shop_title)
    except Shop.DoesNotExist:
        shop = Shop.objects.create(title=shop_title)

    User.objects.create_superuser(username, email, password, shop=shop, work_type=User.WorkType.TYPE_INTERNAL.value, permissions=0xFFFFFFFF)
