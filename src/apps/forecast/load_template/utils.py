import datetime
import json

# from src.main.demand.utils import create_predbills_request_function
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Case, F, Max, Min, TimeField, When
from django.db.models.functions import Greatest, Least
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.response import Response
from src.apps.base.models import Shop, ShopSchedule
from src.interfaces.api.serializers.shop import ShopSerializer
from src.conf.djconfig import HOST
from src.apps.forecast.models import (
    LoadTemplate,
    OperationType,
    OperationTypeName,
    OperationTypeRelation,
    OperationTypeTemplate,
    PeriodClients,
)
from src.apps.timetable.models import WorkType
from src.common.download import xlsx_method


########################## Вспомогательные функции ##########################
def create_operation_type_relations_dict(load_template_id, reverse=False):
    '''
    Создаёт словарь зависимых операций.
    reverse: показывает какая операция будет ключем:
    False - базовая операция
    True - операция от которой есть зависимость
    '''
    key_field = 'base_id'
    type_of_relation = 'depended_id'
    if reverse:
        key_field = 'depended_id'
        type_of_relation = 'base_id'
    operation_type_relations = OperationTypeRelation.objects.filter(base__load_template_id=load_template_id)
    result_dict = {}

    for operation_type_relation in operation_type_relations:
        key = getattr(operation_type_relation, key_field)
        result_dict.setdefault(key, []).append(
            getattr(operation_type_relation, type_of_relation),
        )

    return result_dict


def check_forecasts(shop):
    '''
    Проверяет, что все типы операций спрогнозировались.
    Данную функцию следует вызывать перед apply_formeula.
    '''
    forecast_templates = list(OperationTypeRelation.objects.filter(
        depended__operation_type_name__do_forecast=OperationTypeName.FORECAST,
        depended__load_template_id=shop.load_template_id,
    ).values_list('depended__operation_type_name_id', flat=True))
    operation_types = list(OperationType.objects.filter(
        operation_type_name_id__in=forecast_templates,
        shop=shop, 
        status=OperationType.UPDATED,
    ).values_list('operation_type_name__name', flat=True))
    if len(operation_types):
        return prepare_answer(True, code="not_ready_forecasts", params={'operation_types': operation_types})
    
    return prepare_answer(False)


def prepare_answer(error, code="", result=None, params={}):
    return {
        'error': error,
        'code': code,
        'params':params,
        'result': result,
    }

##############################################################################

def apply_formula(operation_type, operation_type_template, operation_type_relations, shop, dt_from, dt_to, tm_from=None, tm_to=None):
    '''
    Применяет формулу для типа операций.
    Логика частично взята из функции расчета эффективности.
    params:
        operation_type: тип операции для которой делаем расчёт
        operation_type_template: шаблон операции, из которой был создан данный тип опирации
        operation_type_relations: словарь с отношениями типов операций, создается при помощи
            функции create_operation_type_relations_dict
        operation_types_dict: словарь с типами операций в данном магазине, где ключ это id OperationTypeName
        dt_from: дата с которой применяем
        dt_to: дата до которой применяем
        tm_from: время с которого применяем
        tm_to: время до которого применяем

    перед вызовом данной функции необходимо вызвать функцию check_forecasts

    подсчёт ведётся рекурсивно, начиная от конечного типа операций (к которому привязан тип работ)
    пока не будут посчитаны все зависимые операции, результат записан не будет
    порядок расчета зависимых операций не имеет значения, так как невозможны циклические отношения
    '''
    MINUTES_IN_DAY = 24 * 60
    # shop = operation_type.shop
    period_lengths_minutes = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
    period_in_day = MINUTES_IN_DAY // period_lengths_minutes
    tm_from = tm_from if tm_from else operation_type_template.tm_from if operation_type_template.tm_from else datetime.time(0)
    tm_to = tm_to if tm_to else operation_type_template.tm_to if operation_type_template.tm_to else datetime.time(23, 59)
    def dttm2index(dt_init, dttm):
        days = (dttm.date() - dt_init).days
        return days * period_in_day + (dttm.hour * 60 + dttm.minute) // period_lengths_minutes

    def fill_array(array, db_list):
        for model in db_list:
            index = dttm2index(dt_from, model.dttm_forecast)
            array[index] = model.value
    
    def count_res(op_type, template_relation):
        temp_values = np.zeros(((dt_to - dt_from).days + 1)  * period_in_day)
        fill_array(temp_values, PeriodClients.objects.filter(
            operation_type=op_type,
            dttm_forecast__date__gte=dt_from,
            dttm_forecast__date__lte=dt_to,
            dttm_forecast__time__gte=tm_from,
            dttm_forecast__time__lte=tm_to,
            type=PeriodClients.LONG_FORECASE_TYPE,
        ).order_by('dttm_forecast'))
        formula = eval(template_relation.get('formula'))
        try:
            return prepare_answer(False, result=np.array(list(map(formula, temp_values))))
        except (NameError, ValueError) as e:
            return prepare_answer(True, code="error_in_formula_rel", params={
                    'formula': template_relation.get('formula'),
                    'base': operation_type.operation_type_name.name,
                    'depended': template_relation.get("depended").operation_type_name.name,
                    'error': e,
                })
    
    related_templates = operation_type_relations.get(operation_type_template.id, None)
    
    if not related_templates:
        return prepare_answer(True, code="no_relations", params={'operation_type': operation_type})
    result = np.zeros(((dt_to - dt_from).days + 1)  * period_in_day)
    for template_relation in related_templates:
        op_type = OperationType.objects.filter(shop=shop, operation_type_name_id=template_relation.get('depended').operation_type_name_id).first()
        #operation_types_dict.get(template_relation.get('depended').operation_type_name_id)
        if not op_type:
            return prepare_answer(True, code="load_template_not_applied", params={"shop": shop})
        if op_type.status == OperationType.UPDATED:
            res = apply_formula(
                op_type, 
                template_relation.get('depended'), 
                operation_type_relations,
                shop,
                dt_from, 
                dt_to,
            )
            if res['error']:
                return res     
        res = count_res(op_type, template_relation)
        if res['error']:
            return res
        else:
            result += res['result']        
    
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
                    dt_report=dttm.date(),
                    operation_type=operation_type, 
                    value=result[dttm2index(dt_from, dttm)],
                    type=PeriodClients.LONG_FORECASE_TYPE,
                )
            )

    PeriodClients.objects.bulk_create(values_list)
    operation_type.status = OperationType.READY
    operation_type.save()

    return prepare_answer(False)


def create_load_template_for_shop(shop_id, network_id):
    '''
    Создаёт шаблон нагрузки относительно типов операций и типов работ
    определнного магазина.
    '''
    shop = Shop.objects.get(pk=shop_id)

    load_template = LoadTemplate.objects.create(
        name=f'Шаблон нагрузки для магазина {shop.name}',
        network_id=network_id,
    )
    operation_types = OperationType.objects.select_related('work_type').filter(
        shop_id=shop_id, dttm_deleted__isnull=True
    )

    operation_type_templates = [
        OperationTypeTemplate(
            load_template=load_template,
            operation_type_name_id=operation_type.operation_type_name_id,
        )
        for operation_type in operation_types
    ]

    OperationTypeTemplate.objects.bulk_create(operation_type_templates)
    shop.load_template = load_template
    return load_template


def apply_load_template(load_template_id, shop_id):
    '''
    Применяет шаблон нагрузки к магазину. 
    Создает типы операций, типы работ.
    "Удаляет" ненужные типы работ и типы операций.
    Запускает составление прогноза нагрузки.
    '''
    operation_type_templates = LoadTemplate.objects.get(
        pk=load_template_id
    ).operation_type_templates.all() # Получаем шаблоны типов операций
    op_type_names = operation_type_templates.values_list(
        'operation_type_name_id', 
        flat=True
    ) # Названия типов операций которые есть в шаблонах

    for operation_type_template in operation_type_templates.select_related('operation_type_name'):
        work_type = None
        '''
        Если в шаблоне есть тип работ, проверяем
        есть ли он в магазине, и создаём в случае
        необходимости.
        '''
        if operation_type_template.operation_type_name.work_type_name_id:
            work_type, _ = WorkType.objects.get_or_create(
                shop_id=shop_id,
                work_type_name_id=operation_type_template.operation_type_name.work_type_name_id,
            )
            work_type.dttm_deleted = None
            work_type.save()
        '''
        Создаём или обновляем тип операций в соответсвии с шаблоном.
        '''
        OperationType.objects.update_or_create(
            shop_id=shop_id,
            operation_type_name_id=operation_type_template.operation_type_name_id,
            defaults={
                'status': OperationType.UPDATED,
                'work_type': work_type,
                'dttm_deleted': None,
            },
        )
    operation_types = OperationType.objects.filter(shop_id=shop_id).exclude(operation_type_name_id__in=op_type_names)
    '''
    "Удаляем" типы работ и типы операций, которые отсутсвуют в шаблоне.
    '''
    WorkType.objects.filter(operation_type__in=operation_types).update(
        dttm_deleted=timezone.now(),
    )
    operation_types.update(
        dttm_deleted=timezone.now(),
    )
    Shop.objects.filter(pk=shop_id).update(load_template_id=load_template_id)
    # if OperationType.objects.filter(operation_type_name__do_forecast=OperationTypeName.FORECAST, dttm_deleted__isnull=True).exists() and dt_from:
    #     create_predbills_request_function(shop_id, dt=dt_from)


def calculate_shop_load(shop, load_template, dt_from, dt_to, lang='ru'):
    '''
    Расчитывает нагрузку магазина по формулам на определенные даты.
    :params
        shop: Shop obj
        load_template: LoadTemplate obj
        dt_from: datetime.date
        dt_to: datetime.date
        lang: str
    :return
        {
            "error": True | False,
            "code": "code" | "",
            "result": None,
            "params": {},
        }
    '''
    res = check_forecasts(shop)
    if res['error']:
        return res
    # Словарь с конечными типами операций которые расчитываются по формуле
    operation_types_dict = {
        op.operation_type_name_id: op
        for op in OperationType.objects.filter(
            shop=shop, 
            operation_type_name__do_forecast=OperationTypeName.FORECAST_FORMULA,
            work_type__isnull=False,
        )
    }
    operation_type_relations = create_operation_type_relations_dict(shop.load_template_id)
    operation_type_templates = load_template.operation_type_templates.filter(
        operation_type_name__do_forecast=OperationTypeName.FORECAST_FORMULA,
        work_type_name_id__isnull=False,
    )

    for operation_type_template in operation_type_templates:
        operation_type = operation_types_dict.get(operation_type_template.operation_type_name_id)
        if not operation_type:
            return prepare_answer(True, code="load_template_not_applied", params={'shop':shop})
        
        res = apply_formula(
            operation_type, 
            operation_type_template, 
            operation_type_relations, 
            shop,
            dt_from, 
            dt_to, 
        )
        if res['error']:
            return res
    return prepare_answer(False)


'''
Блок кода отвечающий за перерасчёт операций при ручных изменениях
'''
def apply_reverse_formula(operation_type, dt_from, dt_to, tm_from=None, tm_to=None, lang='ru'):
    load_template_id = operation_type.shop.load_template_id
    res = check_forecasts(operation_type.shop)
    if res['error']:
        return res
    operation_type_relations = create_operation_type_relations_dict(load_template_id, reverse=True)
    operation_types = {
        x.operation_type_name_id:x
        for x in OperationType.objects.filter(shop_id=operation_type.shop_id)
    }
    operation_type_template = OperationTypeTemplate.objects.get(
        load_template_id=load_template_id,
        operation_type_name_id=operation_type.operation_type_name_id
    )
    operation_types = set(search_related_operation_types(operation_type, operation_type_relations, operation_type_template, operation_types))
    operation_type_relations = create_operation_type_relations_dict(load_template_id)
    for operation_type in operation_types:
        res = apply_formula(
            operation_type[0], 
            operation_type[1], 
            operation_type_relations, 
            operation_type.shop, 
            dt_from, 
            dt_to, 
            tm_from=tm_from, 
            tm_to=tm_to,
        )
        if res['error']:
            return res
    return prepare_answer(False)


def search_related_operation_types(operation_type, operation_type_relations, operation_type_template, operation_types=None):

    related_templates = operation_type_relations.get(operation_type_template.id)
    result = []
    if not related_templates:
        return result + [(operation_type, operation_type_template), ]
    else:
        for template in related_templates:
            result += search_related_operation_types(
                operation_types.get(template.get('base').operation_type_name_id),
                operation_type_relations, 
                template.get('base'), 
                operation_types,
            )
        return result


def prepare_load_template_request(
        load_template_id,
        shop_id,
        dt_from,
        dt_to,
):
    shop = Shop.objects.get(id=shop_id)
    #TODO SEND ERROR
    forecast_steps = {
        datetime.timedelta(hours=1): '1h',
        datetime.timedelta(minutes=30): '30min',
        datetime.timedelta(days=1): '1d',
    }
    def get_times(tm_from, tm_to):
        if tm_to:
            expression = tm_to
        else:
            expression = F('closes')
        times = ShopSchedule.objects.filter(
            shop_id=shop_id,
            dt__gte=dt_from,
            dt__lte=dt_to,
            type=ShopSchedule.WORKDAY_TYPE,
        ).annotate(
            start=Greatest(F('opens'), tm_from),
            end=Case(
                When(
                    closes=datetime.time(0),
                    then=expression,
                ),
                default=Least(F('closes'), tm_to),
                output_field=TimeField(),
            )
        )
        return list(times.values('dt', 'start', 'end'))

    data = {
        'dt_from': dt_from,
        'dt_to': dt_to,
        'shop': ShopSerializer(shop).data,
        'IP': HOST,
        'forecast_params': json.loads(shop.load_template.forecast_params),
        'round_delta': shop.load_template.round_delta,
    }
    data['shop'].update(shop.load_settings)
    data['shop']['times'] = ShopSchedule.objects.filter(
        shop_id=shop_id,
        dt__gte=dt_from,
        dt__lte=dt_to,
        type=ShopSchedule.WORKDAY_TYPE,
    ).aggregate(
        open=Min('opens'),
        close=Max('closes'),
    )
    relations = {}
    for rel in OperationTypeRelation.objects.filter(
            base__load_template_id=load_template_id,
            type__in=[OperationTypeRelation.TYPE_FORMULA, OperationTypeRelation.TYPE_PREDICTION],
        ).annotate(
            base_name=F('base__operation_type_name_id'),
            depended_name=F('depended__operation_type_name_id'),
        ).values('type', 'formula', 'depended_name', 'base_name'):
        key = rel.get('base_name')
        if not key in relations:
            relations[key] = {}
        rel['formula'] = f'lambda a: {rel["formula"]}'
        relations[key][str(rel.get('depended_name'))] = rel

    templates = list(OperationTypeTemplate.objects.select_related('operation_type_name').filter(load_template_id=load_template_id))
    
    data['operation_types'] = [
        {
            'operation_type_name': o.operation_type_name_id,
            'work_type_name': o.operation_type_name.work_type_name_id,
            'times': get_times(o.tm_from, o.tm_to),
            'forecast_step': forecast_steps.get(o.forecast_step),
            'dependences': relations.get(o.operation_type_name_id, {}),
            'const_value': o.const_value,
            'type': o.operation_type_name.do_forecast,
            'duplicate_over': o.duplicate_over,
            'min_value': o.min_value,
            'max_value': o.max_value,
        }
        for o in templates
    ]
    timeseries = {}
    values = list(PeriodClients.objects.select_related('operation_type').filter(
        operation_type__shop_id=shop_id,
        dttm_forecast__date__gte=dt_from - relativedelta(years=3),
        dttm_forecast__date__lte=dt_to,
        type=PeriodClients.FACT_TYPE,
        operation_type__operation_type_name__operationtypetemplate__load_template_id=load_template_id,
    ).order_by('dttm_forecast'))
    for timeserie in values:
        key = str(timeserie.operation_type.operation_type_name_id)
        if not key in timeseries:
            timeseries[key] = []
        timeseries[key].append(
            {
                'value': timeserie.value,
                'dttm': timeserie.dttm_forecast,
            }
        )
    data['timeserie'] = timeseries
    replace_types = {
        'H': 'F',
        'F': 'O',
        'FS': 'FS',
    }
    for o_type in data['operation_types']:
        o_type['type'] = replace_types[o_type['type']]
    data['change_workload_between'] = [
        {
            'to_serie': rel.base_name, 
            'from_serie': rel.depended_name, 
            'threshold': rel.threshold, 
            'max_value': rel.max_value, 
            'days_of_week': rel.days_of_week_list,
            'order': rel.order,
        }
        for rel in OperationTypeRelation.objects.filter(
            base__load_template_id=load_template_id,
            type=OperationTypeRelation.TYPE_CHANGE_WORKLOAD_BETWEEN,
        ).annotate(
            base_name=F('base__operation_type_name_id'),
            depended_name=F('depended__operation_type_name_id'),
        )
    ]
    return data


def upload_load_template(template_file, form, lang='ru'):
    df = pd.read_excel(template_file)
    network_id = form['network_id']
    o_types = {otn.name: otn for otn in OperationTypeName.objects.filter(network_id=network_id)}
    O_TYPE_COL = df.columns[0]
    DEPENDENCY_COL = df.columns[1]
    FORMULA_COL = df.columns[2]
    CONSTANT_COL = df.columns[3]
    MAX_VALUE_COL = df.columns[4]
    THRESHOLD_COL = df.columns[5]
    ORDER_COL = df.columns[6]
    DAYS_OF_WEEK_COL = df.columns[7]
    TIMESTEP_COL = df.columns[8]
    TM_START_COL = df.columns[9]
    TM_END_COL = df.columns[10]
    o_types_db_set = set(o_types.keys())
    undefined_o_types = set(df[O_TYPE_COL].dropna()).difference(o_types_db_set)
    if len(undefined_o_types):
        raise serializers.ValidationError(_('These operation types do not exist: {types}.').format(types=', '.join(undefined_o_types)))
    bad_dependences = set(df[DEPENDENCY_COL].dropna()).difference(df[O_TYPE_COL].dropna())
    if len(bad_dependences):
        raise serializers.ValidationError(
            _(
                'These operation types listed in dependencies, but not listed in operation types: {types}.'
            ).format(types=', '.join(bad_dependences))
        )
    with transaction.atomic():
        lt = LoadTemplate.objects.create(name=form['name'], network_id=network_id)
        df = df.fillna('')
        df[DAYS_OF_WEEK_COL] = df[DAYS_OF_WEEK_COL].astype(str).str.replace('.', ',', regex=False)
        forecast_steps = {
            '1h': datetime.timedelta(hours=1),
            '30min': datetime.timedelta(minutes=30),
            '1d': datetime.timedelta(days=1),
        }
        templates = []
        for i, row in df.iterrows():
            if not row[O_TYPE_COL] == '':
                if not forecast_steps.get(row[TIMESTEP_COL]):
                    error_msg = _('Error in row {}.').format(i+2) + ' ' + _('Timestep is required.')
                    if row[TIMESTEP_COL]:
                        error_msg = _('Error in row {}.').format(i+2) + ' ' + _(
                            'Timestep {timestep} is not valid choice, choices are {timesteps}.'
                        ).format(
                            timestep=row[TIMESTEP_COL],
                            timesteps=', '.join(forecast_steps.keys()),
                        )
                    raise serializers.ValidationError(error_msg)
                templates.append(
                    OperationTypeTemplate(
                        operation_type_name=o_types[row[O_TYPE_COL]],
                        load_template=lt,
                        tm_from=row[TM_START_COL] or None,
                        tm_to=row[TM_END_COL] or None,
                        forecast_step=forecast_steps.get(row[TIMESTEP_COL]),
                        const_value=row[CONSTANT_COL] or None,
                    )
                )
        templates = OperationTypeTemplate.objects.bulk_create(templates)
        created_templates = {t.operation_type_name.name: t for t in templates}
        prev_name = None
        for i, row in df.iterrows():
            if row[O_TYPE_COL] == '':
                name = prev_name
            else:
                name = row[O_TYPE_COL]
                prev_name = name
            if not row[DEPENDENCY_COL] == '':
                base = created_templates[name]
                depended = created_templates[row[DEPENDENCY_COL]]
                max_value = row[MAX_VALUE_COL]
                threshold = row[THRESHOLD_COL]
                order = row[ORDER_COL]
                days_of_week = []
                type = OperationTypeRelation.TYPE_FORMULA
                if row[DAYS_OF_WEEK_COL]:
                    try:
                        days_of_week = list(map(int, row[DAYS_OF_WEEK_COL].split(',')))
                    except:
                        raise serializers.ValidationError(
                            _('Error in row {}.').format(i+2) + ' ' + _("Invalid days of week '{}', should be comma separated int in interfval from 0 to 6.").format(
                                row[DAYS_OF_WEEK_COL],
                            )
                        )
                OperationTypeRelation.objects.create(
                    base=base,
                    depended=depended,
                    formula=row[FORMULA_COL],
                    max_value=max_value,
                    threshold=threshold,
                    type=type,
                    days_of_week=days_of_week,
                    order=order,
                    row=i + 2,
                )
    return Response()
            

@xlsx_method      
def download_load_template(request, workbook, load_template_id):
    forecast_steps = {
        datetime.timedelta(hours=1): '1h',
        datetime.timedelta(minutes=30): '30min',
        datetime.timedelta(days=1): '1d',
    }
    relations = {}
    for rel in OperationTypeRelation.objects.filter(
            base__load_template_id=load_template_id,
        ).annotate(
            base_name=F('base__operation_type_name_id'),
            depended_name=F('depended__operation_type_name__name'),
        ).values('type', 'formula', 'depended_name', 'base_name', 'max_value', 'threshold', 'days_of_week', 'order'):
        key = rel.get('base_name')
        if not key in relations:
            relations[key] = []
        relations[key].append(rel)
    operation_types = [
        {
            'operation_type_name': o.operation_type_name.name,
            'type': o.operation_type_name.do_forecast,
            'work_type_name_id': o.operation_type_name.work_type_name_id,
            'tm_from': o.tm_from or '',
            'tm_to': o.tm_to or '',
            'const_value': o.const_value or '',
            'forecast_step': forecast_steps.get(o.forecast_step),
            'dependences': relations.get(o.operation_type_name_id, [])
        }
        for o in OperationTypeTemplate.objects.select_related('operation_type_name').filter(load_template_id=load_template_id)
    ]
    operation_ordering = {
        OperationTypeName.FEATURE_SERIE: lambda x: 0,
        OperationTypeName.FORECAST: lambda x: 1 if not x['dependences'] else 2,
        OperationTypeName.FORECAST_FORMULA: lambda x: 3 if not x['work_type_name_id'] else 4,
    }
    operation_types = sorted(operation_types, key=lambda x: operation_ordering[x['type']](x))
    worksheet = workbook.book.add_worksheet('Шаблон нагрузки')
    worksheet.set_column(0, 3, 30)
    worksheet.write(0, 0, 'Тип операции')
    worksheet.write(0, 1, 'Зависимости')
    worksheet.write(0, 2, 'Формула')
    worksheet.write(0, 3, 'Константа')
    worksheet.write(0, 4, 'Максимальное значение')
    worksheet.write(0, 5, 'Порог')
    worksheet.write(0, 6, 'Порядок')
    worksheet.write(0, 7, 'Дни недели (через запятую)')
    worksheet.write(0, 8, 'Шаг прогноза')
    worksheet.write(0, 9, 'Время начала')
    worksheet.write(0, 10, 'Время окончания')
    index = 0
    for ot in operation_types:
        index += 1
        worksheet.write(index, 0, ot['operation_type_name'])
        worksheet.write(index, 3, ot['const_value'])
        worksheet.write(index, 8, ot['forecast_step'])
        worksheet.write(index, 9, str(ot['tm_from']))
        worksheet.write(index, 10, str(ot['tm_to']))
        if len(ot['dependences']):
            index -= 1
            for dependency in ot['dependences']:
                index += 1            
                worksheet.write(index, 1, dependency['depended_name'])
                worksheet.write(index, 2, dependency['formula'] or '')
                worksheet.write(index, 4, dependency['max_value'] or '')
                worksheet.write(index, 5, dependency['threshold'] or '')
                worksheet.write(index, 6, dependency['order'] or '')
                days_of_week = json.loads(dependency['days_of_week'] or '[]')
                worksheet.write(index, 7, ','.join(list(map(str,days_of_week))))
            
    return workbook, 'Load_template'
