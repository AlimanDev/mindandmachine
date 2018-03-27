from src.db.models import CashboxType
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import CashboxTypeConverter
from .forms import GetTypesForm


@api_method('GET', GetTypesForm)
def get_types(request, form):
    filter_params = {
        'shop_id': form.cleaned_data['shop_id']
    }
    if not form.cleaned_data['full']:
        filter_params['dttm_deleted'] = None

    response = [CashboxTypeConverter.convert(x) for x in CashboxType.objects.filter(**filter_params)]
    return JsonResponse.success(response)
