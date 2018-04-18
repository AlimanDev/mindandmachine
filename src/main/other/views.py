from src.db.models import Shop
from src.util.forms import FormUtil
from src.util.models_converter import ShopConverter, SuperShopConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetDepartmentForm


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
