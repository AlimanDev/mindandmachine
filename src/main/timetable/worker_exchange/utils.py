from src.db.models import WorkerDay, WorkerDayCashboxDetails, CashboxType, WorkerCashboxInfo
from django.db.models import Q

import datetime as datetime_module

CHANGE_TYPE_CHOICES = {
    1: 'FROM OTHERSPEC',
    2: 'FROM EVENING TO MORN AND VISA VERSA',
    3: 'EXCESS DAYOFF',
    4: 'OVERWORKINGS',
    5: 'FROM OTHER SPEC, 50%',
    6: 'FROM EVENING IN CASE LESS THAN 5',
    7: 'DAYOFF'
}


def get_key_by_value(dict_, value):
    return list(dict_.keys())[list(dict_.values()).index(value)]


def get_cashiers_working_at_time_on(dttm, ct_ids):
    """
    :param ct_ids: list of CashboxType ids
    :param dttm: datetime obj
    :return: dict{ct_type_id: list of users, working at ct_type}
    """
    if not isinstance(ct_ids, list):
        ct_ids = [ct_ids]
    worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        Q(worker_day__tm_work_end__gte=dttm.time()) & Q(worker_day__tm_work_end__lt=datetime_module.time(23, 59)) |
        Q(worker_day__tm_work_end__lt=datetime_module.time(2, 0)),
        worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
        worker_day__tm_work_start__lte=dttm.time(),
        worker_day__worker_shop=CashboxType.objects.get(id=ct_ids[0]).shop,
        worker_day__dt=dttm.date(),
    )

    ct_user_dict = {}
    for ct_type_id in ct_ids:
        filtered_against_ct_type = worker_day_cashbox_details.filter(cashbox_type_id=ct_type_id)
        ct_user_dict[ct_type_id] = []
        for worker_day_cashbox_details_obj in filtered_against_ct_type:
            if worker_day_cashbox_details_obj.worker_day.worker not in ct_user_dict[ct_type_id]:
                ct_user_dict[ct_type_id].append(worker_day_cashbox_details_obj.worker_day.worker)
    return ct_user_dict


def get_users_who_can_work_on_ct_type(ct_id):
    """

    :param ct_id:
    :return: list of users who can work on cashbox type with id=ct_id
    """
    wci = WorkerCashboxInfo.objects.filter(cashbox_type_id=ct_id, is_active=True)
    users = []
    for wci_obj in wci:
        users.append(wci_obj.worker)
    return users
