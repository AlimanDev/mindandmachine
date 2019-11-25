from .models import (
    CameraCashboxStat,
    CameraCashbox,
    CameraClientGate,
    CameraClientEvent,
)
import datetime
from src.util.utils import outer_server, JsonResponse, api_method
from .forms import CameraStatFrom, CamRequestForm, GetVisitorsInfoForm
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
from django.apps import apps
from datetime import datetime, timedelta, time, date


@csrf_exempt
@api_method('POST', None, auth_required=False, check_permissions=False)
def set_queue(request):
    """
    Обновляет данные по камерам

    Args:
        method: POST
        url: /api/camera/set_queue
        key(str):
        data(str):
    Raises:
        JsonResponse.value_error

    """
    form = CamRequestForm(json.loads(request.body.decode('utf-8')))
    try:
        if not form.is_valid():
            return JsonResponse.value_error(form.errors)
    except:
        return JsonResponse.value_error('not a dictionary')
    if (not settings.QOS_CAMERA_KEY is None) and (form['key'].value() != settings.QOS_CAMERA_KEY):
        return JsonResponse.internal_error('invalid key')

    bad_csf = []
    good_csf = []

    ccs = {cc.name: cc for cc in CameraCashbox.objects.all()}

    for stat in form['data'].value():
        csf = CameraStatFrom(stat)
        if csf.is_valid() and csf.data['name']:
            if csf.data['name'] in ccs.keys():
                cc = ccs[csf.data['name']]
            else:
                cc = CameraCashbox.objects.create(name=csf.data['name'])
                ccs[cc.name] = cc

            cs = csf.save(False)
            cs.camera_cashbox_id = cc.id

            good_csf.append(cs)
            if len(good_csf) > 800:
                CameraCashboxStat.objects.bulk_create(good_csf)
                good_csf = []
        else:
            bad_csf.append([csf.data, csf.errors])
    CameraCashboxStat.objects.bulk_create(good_csf)

    if len(bad_csf):
        return JsonResponse.value_error(json.dumps(bad_csf))
    return JsonResponse.success()


@outer_server()
def set_events(request, json_data):
    """
    Получает данные по посетителям с камер, заносит их в бд

    Args:
        method: POST
        url: /api/camera/set_events
        key(str): ключ
        data(str): payload
    """
    DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

    list_to_create = []

    def bulk_create_camera_event(obj=None):
        if obj is None:
            CameraClientEvent.objects.bulk_create(list_to_create)
        elif len(list_to_create) == 999:
            list_to_create.append(obj)
            CameraClientEvent.objects.bulk_create(list_to_create)
            list_to_create[:] = []
        else:
            list_to_create.append(obj)

    for data_value in json_data:
        dttm = datetime.datetime.strptime(data_value['dttm'], DATETIME_FORMAT)
        event_type = data_value['type']
        if event_type not in [CameraClientEvent.TYPE_BACKWARD, CameraClientEvent.TYPE_TOWARD]:
            return JsonResponse.value_error(
                'no such direction types for gates. Use {} for toward direction, {} for backward'.\
                format(CameraClientEvent.TYPE_TOWARD, CameraClientEvent.TYPE_BACKWARD)
            )

        gate_name = data_value['gate']
        gate_type = data_value['gate_type']
        gate, _ = CameraClientGate.objects.get_or_create(name=gate_name, type=gate_type)
            # return JsonResponse.value_error(
            #     'cannot get gate for gate with name:{} and type: {}'.format(gate_name, gate_type)
            # )
        bulk_create_camera_event(
            CameraClientEvent(
                dttm=dttm,
                gate=gate,
                type=event_type
            )
        )
    bulk_create_camera_event(obj=None)

    return JsonResponse.success()


@api_method('GET', GetVisitorsInfoForm)
def get_visitors_info(request, form):
    """
    Отдает информацию с камер по количеству посетителей

    Args:
        method: GET
        url: /api/demand/get_visitors_info
        from_dt(QOS_DATE): с какой даты смотрим
        to_dt(QOS_DATE):
        shop_id(int): чисто для api_method'a
    Returns:
        {
            'IncomeVisitors': [], |
            'PurchasesOutcomeVisitors': [], |
            'EmptyOutcomeVisitors': []
        }
    """
    def filter_qs(query_set, dttm):
        value_dttm_tuple = list(filter(lambda item_in_qs: item_in_qs[0] == dttm, query_set))
        return value_dttm_tuple[0][1] if value_dttm_tuple else 0

    dttm_from = datetime.combine(form['from_dt'], time())
    dttm_to = datetime.combine(form['to_dt'] + timedelta(days=1), time())

    filter_dict = {
        'type': PeriodClients.FACT_TYPE,
        'dttm_forecast__gte': dttm_from,
        'dttm_forecast__lte': dttm_to,
    }

    return_dict = {
        'IncomeVisitors': [],
        'PurchasesOutcomeVisitors': [],
        'EmptyOutcomeVisitors': []
    }
    query_sets = {}

    for model_name in return_dict.keys():
        query_sets[model_name] = apps.get_model('db', model_name).objects.filter(**filter_dict).values_list(
            'dttm_forecast', 'value'
        )
    dttm = dttm_from
    while dttm < dttm_to:
        for model_name, qs in query_sets.items():
            return_dict[model_name].append({
                'dttm': BaseConverter.convert_datetime(dttm),
                'value': filter_qs(qs, dttm)
            })
        dttm += timedelta(minutes=30)

    return JsonResponse.success(return_dict)