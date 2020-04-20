from src.forecast.models import (
    OperationTypeTemplate, 
    OperationType, 
    PeriodClients, 
    LoadTemplate, 
    OperationTypeRelation,
)
from src.base.models import Shop
from src.timetable.models import WorkType
from src.main.demand.utils import create_predbills_request_function
from src.main.operation_template.utils import build_period_clients
import numpy as np
from django.utils import timezone
import datetime

def create_load_template_for_shop(shop_id):
    shop = Shop.objects.get(pk=shop_id)

    load_template = LoadTemplate.objects.create(
        name=f'Шаблон нагрузки для магазина {shop.name}'
    )
    operation_types = OperationType.objects.select_related('work_type').filter(
        shop_id=shop_id, dttm_deleted__isnull=True
    )

    for operation_type in operation_types:
        OperationTypeTemplate.objects.create(
            load_template=load_template,
            operation_type_name_id=operation_type.operation_type_name_id,
            work_type_name_id=operation_type.work_type.work_type_name_id if operation_type.work_type else None,
            do_forecast=operation_type.do_forecast,
        )
    shop.load_template = load_template
    return load_template


def apply_formula(operation_type, operation_type_template, dt_from, dt_to, tm_from=None, tm_to=None):
    MINUTES_IN_DAY = 24 * 60
    shop = operation_type.shop
    period_lengths_minutes = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
    period_in_day = MINUTES_IN_DAY // period_lengths_minutes
    tm_from = tm_from if tm_from else shop.tm_shop_opens
    tm_to = tm_to if tm_to else shop.tm_shop_closes if shop.tm_shop_closes.hour != 0 else datetime.time(23, 59)
    def dttm2index(dt_init, dttm):
        days = (dttm.date() - dt_init).days
        return days * period_in_day + (dttm.hour * 60 + dttm.minute) // period_lengths_minutes

    def fill_array(array, db_list):
        for model in db_list:
            index = dttm2index(dt_from, model.dttm_forecast)
            array[index] = model.value
    
    def count_res(op_type, template_relation, result):
        temp_values = np.zeros(((dt_to - dt_from).days + 1)  * period_in_day)
        fill_array(temp_values, PeriodClients.objects.filter(
            operation_type=op_type,
            dttm_forecast__date__gte=dt_from,
            dttm_forecast__date__lte=dt_to,
            dttm_forecast__time__gte=tm_from,
            dttm_forecast__time__lte=tm_to,
            type=PeriodClients.LONG_FORECASE_TYPE,
        ).order_by('dttm_forecast'))
        formula = eval(template_relation.formula)
        division_val = period_lengths_minutes if template_relation.convert_min_to_real else 1
        try:
            return (result + formula(temp_values)/division_val, True)
        except:
            try:
                return (result + np.array(list(map(formula, temp_values)))/division_val, True)
            except:
                error_mes = f'There is an error in formula in relation between {template_relation.base.operation_type_name.name} ' + \
                    f'and {template_relation.depended.operation_type_name.name}'
                return (error_mes, False)

    forecast_templates = list(OperationTypeRelation.objects.filter(
        base=operation_type_template, depended__do_forecast=OperationType.FORECAST
    ).values_list('depended__operation_type_name_id', flat=True))

    if OperationType.objects.filter(
        operation_type_name_id__in=forecast_templates,
        shop=shop, 
        status=OperationType.UPDATED,
    ).exists():
        return ('There is not ready forecasts!', False)
    
    operation_types_dict = {
        op.operation_type_name_id: op
        for op in OperationType.objects.filter(shop=shop)
    }

    related_templates = list(OperationTypeRelation.objects.select_related('depended').filter(
        base=operation_type_template
    ))
    if not len(related_templates):
        return (
            f'Do_forecast of operation type {operation_type.operation_type_name.name} is formula but there is not any relations',
            False,
        )
    result = np.zeros(((dt_to - dt_from).days + 1)  * period_in_day)
    for template_relation in related_templates:
        op_type = operation_types_dict.get(template_relation.depended.operation_type_name_id)
        if not op_type:
            return (f'Load template is not applied in shop {operation_type.shop.name}', False)
        if op_type.status == OperationType.UPDATED:
            res = apply_formula(op_type, template_relation.depended, dt_from, dt_to)
            if not res[1]:
                return res     
        res = count_res(op_type, template_relation, result)
        if res[1]:
            result = res[0]
        else:
            return res
    
    PeriodClients.objects.filter(
        operation_type=operation_type,
        dttm_forecast__date__gte=dt_from,
        dttm_forecast__date__lte=dt_to,
        dttm_forecast__time__gte=tm_from,
        dttm_forecast__time__lte=tm_to,
        type=PeriodClients.LONG_FORECASE_TYPE,
    ).delete()
    values_list = []

    for day in range((dt_to - dt_from).days + 1):
        for period in range(MINUTES_IN_DAY // period_lengths_minutes):
            dttm = datetime.datetime.combine(
                dt_from + datetime.timedelta(days=day), 
                datetime.time(
                    hour=period * period_lengths_minutes // 60,
                    minute=period * period_lengths_minutes % 60
                )
            )
            if dttm.time() > tm_to or dttm.time() < tm_from:
                continue
            values_list.append(
                PeriodClients(
                    dttm_forecast=dttm, 
                    operation_type=operation_type, 
                    value=result[dttm2index(dt_from, dttm)],
                    type=PeriodClients.LONG_FORECASE_TYPE,
                )
            )

    PeriodClients.objects.bulk_create(values_list)
    operation_type.status = OperationType.READY
    operation_type.save()

    return ('Created', True)


def apply_reverse_formula(operation_type, dt_from, dt_to, tm_from=None, tm_to=None):
    operation_types = set(search_related_operation_types(operation_type))
    for operation_type in operation_types:
        res = apply_formula(operation_type[0], operation_type[1], dt_from, dt_to, tm_from=tm_from, tm_to=tm_to)
        if not res[1]:
            return res
    return ('Updated', True)


def search_related_operation_types(operation_type, operation_type_template=None, operation_types=None):
    if not operation_type_template:
        operation_type_template = operation_type.shop.load_template.operation_type_templates.get(
            operation_type_name_id=operation_type.operation_type_name_id,
        )
    
    if not operation_types:
        operation_types = {
            x.operation_type_name_id:x
            for x in OperationType.objects.filter(shop_id=operation_type.shop_id)
        }

    related_templates = OperationTypeRelation.objects.select_related('base').filter(
        depended=operation_type_template,
    )
    result = []
    if not related_templates.exists():
        return result + [(operation_type, operation_type_template), ]
    else:
        for template in related_templates:
            result += search_related_operation_types(
                operation_types.get(template.base.operation_type_name_id), 
                operation_type_template=template.base, 
                operation_types=operation_types
            )
        return result


def apply_load_template(load_template_id, shop_id, dt_from):
    operation_type_templates = LoadTemplate.objects.get(
        pk=load_template_id
    ).operation_type_templates.all()
    op_type_names = operation_type_templates.values_list('operation_type_name_id', flat=True)

    for operation_type_template in operation_type_templates:
        work_type = None
        if operation_type_template.work_type_name:
            try:
                work_type = WorkType.objects.get(
                    shop_id=shop_id,
                    work_type_name=operation_type_template.work_type_name,
                )
            except:
                work_type = WorkType.objects.create(
                    shop_id=shop_id,
                    work_type_name=operation_type_template.work_type_name,
                )

        try:
            operation_type = OperationType.objects.get(
                shop_id=shop_id,
                operation_type_name=operation_type_template.operation_type_name,
            )

            operation_type.status = OperationType.UPDATED \
                if operation_type_template.do_forecast != OperationType.FORECAST_NONE\
                else OperationType.READY
            operation_type.work_type = work_type
            operation_type.do_forecast = operation_type_template.do_forecast
            operation_type.dttm_deleted = None
            operation_type.save()
        except:
            operation_type = OperationType.objects.create(
                shop_id=shop_id,
                operation_type_name=operation_type_template.operation_type_name,
                do_forecast=operation_type_template.do_forecast,
                status=OperationType.UPDATED \
                if operation_type_template.do_forecast != OperationType.FORECAST_NONE\
                else OperationType.READY,
                work_type=work_type,
            )
    operation_types = OperationType.objects.filter(shop_id=shop_id).exclude(operation_type_name_id__in=op_type_names)
    WorkType.objects.filter(operation_type__in=operation_types).update(
        dttm_deleted=timezone.now(),
    )
    operation_types.update(
        dttm_deleted=timezone.now(),
    )
    Shop.objects.filter(pk=shop_id).update(load_template_id=load_template_id)
    if OperationType.objects.filter(do_forecast=OperationType.FORECAST, dttm_deleted__isnull=True).exists():
        create_predbills_request_function(shop_id, dt=dt_from)


def calculate_shop_load(shop, load_template, dt_from, dt_to):
    operation_types_dict = {
        op.operation_type_name_id: op
        for op in OperationType.objects.filter(
            shop=shop, 
            do_forecast=OperationType.FORECAST_FORMULA,
            work_type__isnull=False,
        )
    }

    operation_type_templates = load_template.operation_type_templates.filter(
        do_forecast=OperationType.FORECAST_FORMULA,
        work_type_name_id__isnull=False,
    )

    for operation_type_template in operation_type_templates:
        operation_type = operation_types_dict.get(operation_type_template.operation_type_name_id)
        if not operation_type:
            return (f'Load template is not applied in shop {shop.name}', False)
        
        res = apply_formula(operation_type, operation_type_template, dt_from, dt_to)
        if not res[1]:
            return res

    return ('Calculated', True)
