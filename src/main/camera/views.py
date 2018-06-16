from src.db.models import CameraCashboxStat, CameraCashbox
from src.util.utils import api_method, JsonResponse
from .forms import CameraStatFrom, CamRequestForm
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json
from .forms import CameraStatFrom


@csrf_exempt
@api_method('POST', None, auth_required=False)
def set_queue(request):
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

def agrigate_cameras():
    pass

@api_method('GET', CameraStatFrom)
def get_queue_from_cameras(request, form):
    try:
        dttm = form['dttm']
        queue = form['queue']
        print('--------------',queue,dttm)
    except:
        pass
        # return JsonResponse.value_error('Cannot get shop')
    #
    # return JsonResponse.success({
    #     'mean_queue_length': shop.mean_queue_length,
    #     'max_queue_length': shop.max_queue_length,
    #     'dead_time_part': shop.dead_time_part
    # })
