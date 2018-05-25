from src.db.models import CameraCashboxStat, CameraCashbox
from src.util.utils import api_method, JsonResponse
from .forms import CameraStatFrom, CamRequestForm
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import json


@csrf_exempt
@api_method('POST', None, auth_required=False)
def set_queue(request):
    form = CamRequestForm(json.loads(request.body.decode('utf-8')))
    try:
        if not form.is_valid():
            return JsonResponse.value_error(form.errors)
    except:
        return JsonResponse.value_error('not a dictionary')
    if (not settings.QOS_CAMERA_KEY is None) and (form['key'] == settings.QOS_SET_TIMETABLE_KEY):
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

