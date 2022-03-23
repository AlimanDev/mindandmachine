import pandas as pd
from datetime import timedelta, datetime, time
from src.forecast.models import OperationTypeName, OperationTypeTemplate, PeriodClients, OperationType
from src.base.models import Shop
from django.db import transaction

def fill_empty_values_with_zero(operation_type_name_ids=[], dttm_from=None, dttm_to=None):
    names_filter = {}
    if operation_type_name_ids:
        names_filter['id__in'] = operation_type_name_ids

    dttms_filter = {}
    if dttm_from:
        dttms_filter['dttm_forecast__gte'] = dttm_from
    if dttm_to:
        dttms_filter['dttm_forecast__lte'] = dttm_to
    
    names = {n.id: n.name for n in OperationTypeName.objects.filter(do_forecast=OperationTypeName.FORECAST, **names_filter)}

    operation_templates = {}

    for ot in OperationTypeTemplate.objects.filter(operation_type_name_id__in=names.keys()): 
        operation_templates.setdefault(ot.load_template_id, {})[ot.operation_type_name_id] = ot.forecast_step 

    shops = Shop.objects.filter(load_template__isnull=False)

    operation_types = {}

    for ot in OperationType.objects.filter(shop__in=shops, operation_type_name_id__in=names.keys()):
        operation_types.setdefault(ot.shop_id, {})[ot.operation_type_name_id] = ot

    clients_to_create = []

    for shop in shops:
        for name_id, ot in operation_types.get(shop.id, {}).items():
            data_days = list(
                PeriodClients.objects.filter(
                    type=PeriodClients.FACT_TYPE, 
                    operation_type=ot,
                    **dttms_filter,
                ).values(
                    'dttm_forecast__date',
                ).distinct().order_by(
                    'dttm_forecast__date',
                ).values_list('dttm_forecast__date', flat=True)
            )
            if not data_days:
                continue
            dates = pd.date_range(data_days[0], data_days[-1], freq='1d').date
            no_data_dates = set(dates) - set(data_days)
            for dt in no_data_dates:
                timestep = operation_templates[shop.load_template_id][name_id]
                if timestep == timedelta(1):
                    clients_to_create.append(PeriodClients(dttm_forecast=datetime.combine(dt, time(0)), value=0, operation_type=ot, type=PeriodClients.FACT_TYPE))
                    continue
                schedule = shop.get_schedule(dt)
                if not schedule:
                    continue
                dttms = pd.date_range(dt, dt + timedelta(1), freq=timestep)
                dttms = dttms[(dttms.time >= schedule['tm_open']) & (dttms.time <= schedule['tm_close'])]
                clients_to_create.extend(
                    [
                        PeriodClients(dttm_forecast=dttm, value=0, operation_type=ot, type=PeriodClients.FACT_TYPE)
                        for dttm in dttms
                    ]
                )
    with transaction.atomic():
        PeriodClients.objects.bulk_create(clients_to_create)
