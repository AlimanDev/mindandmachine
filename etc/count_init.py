from src.db.models import Shop, WorkType
import pandas as pd
from src.main.timetable.cashier_demand.utils import get_worker_timetable2


def count_hours(dt_from, dt_to):
    type_dict = []

    for shop in Shop.objects.all():
        for wt in WorkType.objects.filter(shop=shop, dttm_deleted__isnull=True):
            form = {
                'from_dt': dt_from,
                'to_dt': dt_to,
                'work_type_ids': [wt.id],
            }
            res = get_worker_timetable2(shop.id, form)
            res = res['indicators']
            type_dict.append({
                'Магазин': shop.title,
                'Часы по алгоритму': res['total_go_initial'],
                'Часы от сотрудников': res['total_go'],
            })

    return pd.DataFrame(type_dict)

