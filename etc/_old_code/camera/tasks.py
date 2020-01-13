from datetime import timedelta

from django.db.models import Avg
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta

from src.db.models import (
    # PeriodQueues,
    WorkType,
)

from .models import (
    CameraClientEvent,
    CameraCashboxStat,
    CameraClientGate,

    IncomeVisitors,
    EmptyOutcomeVisitors,
    PurchasesOutcomeVisitors,
)

from src.celery.celery import app


@app.task
def update_queue(till_dttm=None):
    """
    Обновляет данные по очереди на всех типах касс

    Args:
        till_dttm(datetime.datetime): до какого времени обновлять?

    Note:
        Выполняется каждые полчаса
    """
    time_step = timedelta(seconds=1800)  # todo: change to supershop step
    if till_dttm is None:
        till_dttm = now() + timedelta(hours=3)  # moscow time

    work_types = WorkType.objects.qos_filter_active(till_dttm + timedelta(minutes=30), till_dttm).filter(
        dttm_last_update_queue__isnull=False,
    )
    if not len(work_types):
        raise ValueError('WorkType EmptyQuerySet with dttm_last_update_queue')
    for work_type in work_types:
        dif_time = till_dttm - work_type.dttm_last_update_queue
        while dif_time > time_step:
            mean_queue = list(CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox__type__id=work_type.id,
                dttm__gte=work_type.dttm_last_update_queue,
                dttm__lt=work_type.dttm_last_update_queue + time_step
            ).values('camera_cashbox_id').annotate(mean_queue=Avg('queue')).values_list('mean_queue', flat=True)) #.filter(mean_queue__gte=0.5)
            # todo: mean_queue__gte seems stupid -- need to change and look only open

            if len(mean_queue):

                min_possible_period_len = max(mean_queue) * 0.17
                mean_queue = list([el for el in mean_queue if el > min_possible_period_len and el > 0.4])
                mean_queue = sum(mean_queue) / (len(mean_queue) + 0.000001)

                changed_amount = PeriodQueues.objects.filter(
                    dttm_forecast=work_type.dttm_last_update_queue,
                    operation_type_id=work_type.work_type_reversed.all()[0].id,
                    type=PeriodQueues.FACT_TYPE,
                ).update(value=mean_queue)
                if changed_amount == 0:
                    PeriodQueues.objects.create(
                        dttm_forecast=work_type.dttm_last_update_queue,
                        type=PeriodQueues.FACT_TYPE,
                        value=mean_queue,
                        operation_type_id=work_type.work_type_reversed.all()[0].id,
                    )

            work_type.dttm_last_update_queue += time_step
            dif_time -= time_step
        work_type.save()


@app.task
def update_visitors_info():
    timestep = timedelta(minutes=30)
    dttm_now = now()
    # todo: исправить потом. пока делаем такую привязку
    # вообще хорошей идеей наверное будет просто cashbox_type blank=True, null=True сделать в PeriodDemand
    try:
        work_type = WorkType.objects.get(work_type_name__name='Кассы', shop_id=1)
    except WorkType.DoesNotExist:
        raise ValueError('Такого типа касс нет в базе данных.')
    create_dict = {
        'work_type': work_type,
        'dttm_forecast': dttm_now.replace(minute=(0 if dttm_now.minute < 30 else 30), second=0, microsecond=0),
        'type': IncomeVisitors.FACT_TYPE
    }

    events_qs = CameraClientEvent.objects.filter(
        dttm__gte=dttm_now - timestep,
        dttm__lte=dttm_now
    )

    income_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_ENTRY,
        type=CameraClientEvent.TYPE_TOWARD,
    ).count()
    empty_outcome_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_ENTRY,
        type=CameraClientEvent.TYPE_BACKWARD,
    ).count()
    purchases_outcome_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_OUT,
        type=CameraClientEvent.TYPE_TOWARD,
    ).count() - events_qs.filter(
        gate__type=CameraClientGate.TYPE_OUT,
        type=CameraClientEvent.TYPE_BACKWARD,
    ).count()

    IncomeVisitors.objects.create(
        value=income_visitors_value,
        **create_dict
    )
    EmptyOutcomeVisitors.objects.create(
        value=empty_outcome_visitors_value,
        **create_dict
    )
    PurchasesOutcomeVisitors.objects.create(
        value=purchases_outcome_visitors_value,
        **create_dict
    )

    print('успешно создал стату по покупателям')


@app.task
def clean_camera_stats():
    """
    Удаляет данные с камер за последние for_past_months месяцев

    Note:
        Запускается раз в неделю
    """
    for_past_months = 3
    dttm_to_delete = now() - relativedelta(months=for_past_months)

    CameraCashboxStat.objects.filter(dttm__lt=dttm_to_delete).delete()

