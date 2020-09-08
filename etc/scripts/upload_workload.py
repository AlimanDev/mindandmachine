import pandas as pd
from src.base.models import (
    Shop,
)
from src.forecast.models import (
    OperationType,
    PeriodClients,

)


def upload_workload2shop(file_path, shop_id):
    shop = Shop.objects.get(id=shop_id)
    new_workload = pd.read_excel(file_path)
    dttm_min = new_workload.dttm.min()
    dttm_max = new_workload.dttm.max()

    for worktype in set(new_workload.columns) - {'dttm'}:
        operation = OperationType.objects.get(
            work_type__shop=shop,
            work_type__work_type_name__name=worktype
        )
        PeriodClients.objects.filter(
            dttm_forecast__gte=dttm_min,
            dttm_forecast__lte=dttm_max,
            operation_type=operation,
            type=PeriodClients.LONG_FORECASE_TYPE
        ).delete()
        PeriodClients.objects.bulk_create([
            PeriodClients(
                dttm_forecast=row['dttm'],
                operation_type=operation,
                type=PeriodClients.LONG_FORECASE_TYPE,
                value=row[worktype]

            ) for _, row in new_workload[['dttm', worktype]].iterrows()
        ])

