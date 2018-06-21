from datetime import timedelta

from src.db.models import CameraCashboxStat, Cashbox, WorkerDayCashboxDetails
from django.db.models import Avg

from src.util.utils import api_method, JsonResponse
from .forms import GetCashboxesInfo
from django.utils.timezone import now


@api_method('GET', GetCashboxesInfo)
def get_cashboxes_info(request, form):
    response = {}
    time = now()
    shop_id = form['shop_id']

    list_of_cashbox = Cashbox.objects.qos_filter_active(time,
                                                        time,
                                                        type__shop__id=shop_id).order_by('number')
    for cashbox in list_of_cashbox:

        if cashbox.type.dttm_last_update_queue is None:
            with_queue = False

        else:
            with_queue = True
            mean_queue = CameraCashboxStat.objects.all().filter(camera_cashbox__cashbox__id=cashbox.id,
                                                                dttm__gte=time - timedelta(seconds=60),
                                                                dttm__lt=time).values(
                'queue').aggregate(mean_queue=Avg('queue'))

        if not mean_queue['mean_queue']:
            mean_queue['mean_queue'] = 0

        status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
                                                                                     on_cashbox__id=cashbox.id,
                                                                                     tm_from__lt=time.time(),
                                                                                     tm_to__gte=time.time(),
                                                                                     on_cashbox=cashbox.id,
                                                                                     cashbox_type__id=cashbox.type.id,
                                                                                     worker_day__dt=time.date(),
                                                                                     worker_day__worker_shop__id=shop_id
                                                                                     )
        user_id = 'no_user'

        if not status:
            status = 'C'
        else:
            status = 'O'

            for item in status:
                u_id = str(item.worker_day.worker.id)
                if user_id:
                    user_id = u_id

        if cashbox.type.id in response:
            response[cashbox.type.id]["кассы"] += {
                                                      "number": cashbox.number,
                                                      "status": status,
                                                      "queue": mean_queue['mean_queue'],
                                                      "user_id": user_id,
                                                  },
        else:
            response.update({cashbox.type.id: {
                "name": cashbox.type.name,
                "with_queue": with_queue,
                "кассы": [
                    {
                        "number": cashbox.number,
                        "status": status,
                        "queue": mean_queue['mean_queue'],
                        "user_id": user_id,
                    }, ]}, })

    return JsonResponse.success(response)
