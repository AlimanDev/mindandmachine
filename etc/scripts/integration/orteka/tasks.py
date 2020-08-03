from datetime import timedelta, datetime

from src.base.models import (
    Shop,
)
from src.forecast.models import (
    PeriodClients,
    Receipt,
    OperationType,
    OperationTypeName
)
from src.celery.celery import app
import json


@app.task
def aggregate_receipts():
    try:
        income_otn = OperationTypeName.objects.get(code='income')
    except OperationTypeName.DoesNotExist:
        raise Exception("Income operation type does not exist")

    try:
        receipt_otn = OperationTypeName.objects.get(code='receipt')
    except OperationTypeName.DoesNotExist:
        raise Exception("Receipt operation type does not exist")

    for shop in Shop.objects.all():
        receipt_dttm = {}
        income_dttm = {}
        try:
            income_ot = OperationType.objects.get(operation_type_name=income_otn, shop=shop)
        except OperationType.DoesNotExist:
            print(f"income operation type does not exist for {shop}")
            continue
        try:
            receipt_ot = OperationType.objects.get(operation_type_name=receipt_otn, shop=shop)
        except OperationType.DoesNotExist:
            print(f"receipt operation type does not exist for {shop}")
            continue

        receipts = Receipt.objects.filter(is_aggregated=False, shop=shop)
        for receipt in receipts:
            info = json.loads(receipt.info)
            forecast_int = shop.forecast_step_minutes
            interval = timedelta(
                hours=forecast_int.hour,
                minutes=forecast_int.minute,
                seconds=forecast_int.second,
                microseconds=forecast_int.microsecond)
            interval = interval.total_seconds()
            dttm = int(receipt.dttm.timestamp() // interval * interval)

            print(dttm)
            print(income_dttm)
            if dttm not in income_dttm:
                print('create')
                income_dttm[dttm] = 0

            income_dttm[dttm] += float(info['СуммаДокумента'])

            if dttm not in receipt_dttm:
                receipt_dttm[dttm] = 0
            receipt_dttm[dttm] += 1

        pc_list = []
        for dttm, amount in receipt_dttm.items():
            pc_list.append(PeriodClients(
                dttm_forecast=datetime.fromtimestamp(dttm),
                value=amount,
                operation_type=receipt_ot,
                type=PeriodClients.FACT_TYPE
            ))

        for dttm, amount in income_dttm.items():
            pc_list.append(PeriodClients(
                dttm_forecast=datetime.fromtimestamp(dttm),
                value=amount,
                operation_type=income_ot,
                type=PeriodClients.FACT_TYPE
            ))
        PeriodClients.objects.bulk_create(pc_list)
        receipts.update(is_aggregated=True)
