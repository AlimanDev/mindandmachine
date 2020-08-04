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
import numpy as np
from django.utils import timezone
import datetime


########################## Вспомогательные функции ##########################
def create_operation_type_relations_dict(load_template_id, reverse=False):
    '''
    Создаёт словарь зависимых операций.
    reverse: показывает какая операция будет ключем:
    False - базовая операция
    True - операция от которой есть зависимость
    '''
    type_of_relation = 'depended'
    if reverse:
        type_of_relation = 'base'
    operation_type_relations = OperationTypeRelation.objects.select_related(type_of_relation).filter(base__load_template_id=load_template_id)
    result_dict = {}

    for operation_type_relation in operation_type_relations:
        key = operation_type_relation.base_id
        if key not in result_dict:
            result_dict[key] = []
        result_dict[key].append(
            {
                type_of_relation: getattr(operation_type_relation, type_of_relation),
                'formula': operation_type_relation.formula,
            }
        )

    return result_dict


def check_forecasts(shop):
    '''
    Проверяет, что все типы операций спрогнозировались.
    Данную функцию следует вызывать перед apply_formeula.
    '''
    forecast_templates = list(OperationTypeRelation.objects.filter(
        depended__do_forecast=OperationType.FORECAST,
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
    tm_from = tm_from if tm_from else datetime.time(0)
    tm_to = tm_to if tm_to else datetime.time(23, 59)
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
                    operation_type=operation_type, 
                    value=result[dttm2index(dt_from, dttm)],
                    type=PeriodClients.LONG_FORECASE_TYPE,
                )
            )

    PeriodClients.objects.bulk_create(values_list)
    operation_type.status = OperationType.READY
    operation_type.save()

    return prepare_answer(False)


def create_load_template_for_shop(shop_id):
    '''
    Создаёт шаблон нагрузки относительно типов операций и типов работ
    определнного магазина.
    '''
    shop = Shop.objects.get(pk=shop_id)

    load_template = LoadTemplate.objects.create(
        name=f'Шаблон нагрузки для магазина {shop.name}'
    )
    operation_types = OperationType.objects.select_related('work_type').filter(
        shop_id=shop_id, dttm_deleted__isnull=True
    )

    operation_type_templates = [
        OperationTypeTemplate(
            load_template=load_template,
            operation_type_name_id=operation_type.operation_type_name_id,
            work_type_name_id=operation_type.work_type.work_type_name_id if operation_type.work_type else None,
            do_forecast=operation_type.do_forecast,
        )
        for operation_type in operation_types
    ]

    OperationTypeTemplate.objects.bulk_create(operation_type_templates)
    shop.load_template = load_template
    return load_template


def apply_load_template(load_template_id, shop_id, dt_from):
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

    for operation_type_template in operation_type_templates:
        work_type = None
        '''
        Если в шаблоне есть тип работ, проверяем
        есть ли он в магазине, и создаём в случае
        необходимости.
        '''
        if operation_type_template.work_type_name_id:
            work_type, _ = WorkType.objects.get_or_create(
                shop_id=shop_id,
                work_type_name_id=operation_type_template.work_type_name_id,
            )
        '''
        Создаём или обновляем тип операций в соответсвии с шаблоном.
        '''
        OperationType.objects.update_or_create(
            shop_id=shop_id,
            operation_type_name_id=operation_type_template.operation_type_name_id,
            defaults={
                'status': OperationType.UPDATED \
                if operation_type_template.do_forecast != OperationType.FORECAST_NONE\
                else OperationType.READY,
                'work_type': work_type,
                'do_forecast': operation_type_template.do_forecast,
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
    if OperationType.objects.filter(do_forecast=OperationType.FORECAST, dttm_deleted__isnull=True).exists():
        create_predbills_request_function(shop_id, dt=dt_from)


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
            do_forecast=OperationType.FORECAST_FORMULA,
            work_type__isnull=False,
        )
    }
    operation_type_relations = create_operation_type_relations_dict(shop.load_template_id)
    operation_type_templates = load_template.operation_type_templates.filter(
        do_forecast=OperationType.FORECAST_FORMULA,
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
