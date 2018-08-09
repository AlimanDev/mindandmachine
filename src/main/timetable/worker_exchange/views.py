from src.db.models import (
    User,
)
from .forms import (
    GetWorkersToExchange
)
from .utils import (
    get_users_who_can_work_on_ct_type,
    ChangeTypeFunctions,
    get_init_params
)
from src.util.utils import api_method, JsonResponse
from src.util.models_converter import UserConverter


@api_method('GET', GetWorkersToExchange)
def get_workers_to_exchange(request, form):
    ct_type = form['specialization']
    dttm_exchange = form['dttm']
    shop_id = form['shop_id'] if form['shop_id'] else request.user.shop_id

    users_who_can_work_on_ct = get_users_who_can_work_on_ct_type(ct_type)

    init_params_dict = get_init_params(dttm_exchange, shop_id)

    default_function_dict = {
        'shop_id': shop_id,
        'dttm_exchange': dttm_exchange,
        'ct_type': ct_type,
        'predict_demand': init_params_dict['predict_demand'],
        'mean_bills_per_step': init_params_dict['mean_bills_per_step'],
        'cashbox_types': init_params_dict['cashbox_types_hard_dict'],
        'users_who_can_work': users_who_can_work_on_ct
    }

    result_dict = {}
    for f in ChangeTypeFunctions:
        func_result_dict = f(default_function_dict)
        for user_id in func_result_dict:
            if user_id in result_dict.keys():
                if func_result_dict[user_id]['type'] < result_dict[user_id]['type']:
                    result_dict[user_id]['type'] = func_result_dict[user_id]['type']
            else:
                result_dict[user_id] = {}
                result_dict[user_id].update(func_result_dict[user_id])

    for k in result_dict.keys():
        result_dict[k].update({'user_info': UserConverter.convert(User.objects.get(id=k))})

    return JsonResponse.success(result_dict)

