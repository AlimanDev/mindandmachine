from src.db.models import CashboxType
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import CashboxTypeConverter
from .forms import GetTypesForm


@api_method('GET', GetTypesForm)
def get_types(request, form):
    filter_params = {
        'shop_id': form['shop_id']
    }
    if not form['full']:
        filter_params['dttm_deleted'] = None

    types = {x.name: x for x in CashboxType.objects.filter(**filter_params)}

    types_result = []

    def __add_t(__s):
        __x = types.pop(__s, None)
        if __x is not None:
            types_result.append(__x)

    __add_t('Линия')
    __add_t('Возврат')

    for x in types.values():
        types_result.append(x)

    response = [CashboxTypeConverter.convert(x) for x in types_result]
    return JsonResponse.success(response)
