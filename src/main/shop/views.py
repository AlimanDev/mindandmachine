from src.db.models import Shop
from src.util.utils import api_method, JsonResponse
from src.util.forms import FormUtil
from src.util.models_converter import BaseConverter
from .forms import (
    GetParametersForm,
    SetParametersForm,
)


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
    Shop.objects.get(id=102)

    shop.mean_queue_length = form['queue_length']
    shop.idle = form['idle']
    shop.fot = form['fot']
    shop.less_norm = form['less_norm']
    shop.more_norm = form['more_norm']
    shop.tm_shop_opens = form['tm_shop_opens']
    shop.tm_shop_closes = form['tm_shop_closes']
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
