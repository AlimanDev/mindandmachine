from django.utils.timezone import now

from datetime import datetime, timedelta
import json

from .utils import build_period_clients
from src.db.models import (
    OperationTemplate,
    OperationType,
    Shop
)

from src.util.utils import JsonResponse, api_method
from src.util.models_converter import (
    OperationTemplateConverter,
)
from .forms import (
    GetOperationTemplatesForm,
    CreateOperationTemplateForm,
    DeleteOperationTemplateForm,
    UpdateOperationTemplateForm,
    OperationTemplateForm
)


@api_method('GET', GetOperationTemplatesForm,
    lambda_func=lambda x:
        OperationType.objects.get(id=x['operation_type_id']).work_type.shop \
            if x['operation_type_id'] else Shop.objects.get(id=x['shop_id'])
)
def get_operation_templates(request, form):
    """
    Возвращает список шаблонов операций для shop_id или operation_type_id

    Args:
        method: GET
        url: api/operation_template/get_operation_templates
        operation_type_id: тип операции
        #shop_id(int): required = True
        #from_dt(QOS_DATE): required = False
        #to_dt(QOS_DATE): required = False

    Returns:
        [
            {
                | 'id': id шаблона,
                | 'name': название,
                | 'tm_start': время начала работ,
                | 'tm_end': время окончания работ,
                | 'value': количество человек,
                | 'period': ежедневно, неделя, месяц,
                | 'days_in_period': массив с номерами дней в неделе или месяце,
                | 'operation_type_id': id типа операции,
                | 'dttm_added': ,
                | 'dttm_deleted': ,
            }, ...
        ]
    """
    shop = request.shop

    operation_templates = OperationTemplate.objects.filter(
        dttm_deleted=None,
    )
    if form['operation_type_id']:
        operation_templates=operation_templates.filter(
            operation_type_id=form['operation_type_id'],
        )
    else:
        operation_templates=operation_templates.filter(
            operation_type__work_type__shop_id=shop.id,
        )

    return JsonResponse.success(
        [OperationTemplateConverter.convert(x) for x in operation_templates]
    )


@api_method(
    'POST',
    CreateOperationTemplateForm,
    lambda_func=lambda x: OperationType.objects.get(id=x['operation_type_id']).work_type.shop
)
def create_operation_template(request, form):
    """
    Создает новый шаблон операции

    Args:
        method: POST
        url: /api/operation_template/create_operation_template
        'name': название,
        'tm_start': время начала работ,
        'tm_end': время окончания работ,
        'value': количество человек,
        'period': ежедневно, неделя, месяц,
        'days_in_period': массив с номерами дней в неделе или месяце,
            [1,7] для недели,
            [1,31] для месяца.
            Отсутствующий день в месяце пропускается
        'operation_type_id': id типа операции,

    Returns:
        {
            | 'id': id шаблона,
            | 'name': название,
            | 'tm_start': время начала работ,
            | 'tm_end': время окончания работ,
            | 'value': количество человек,
            | 'period': ежедневно, неделя, месяц,
            | 'days_in_period': массив с номерами дней в неделе или месяце,
            | 'operation_type_id': id типа операции,
            | 'dttm_added': ,
            | 'dttm_deleted': ,
        }
    """

    operation_template = OperationTemplate.objects.create(
        name=form['name'],
        tm_start=form['tm_start'],
        tm_end=form['tm_end'],
        value=form['value'],
        period=form['period'],
        days_in_period=form['days_in_period'],
        operation_type_id=form['operation_type_id'],
    )

    return JsonResponse.success(
        OperationTemplateConverter.convert(operation_template)
    )


@api_method(
    'POST',
    DeleteOperationTemplateForm,
    lambda_func=lambda x: OperationTemplate.objects.get(id=x['id']).operation_type.work_type.shop
)
def delete_operation_template(request, form):
    """
    "Удаляет" шаблон операции с заданным номером

    Args:
        method: POST
        url: /api/operation_template/delete_operation_template
        id(int): required = True

    Returns:

    """

    operation_template = OperationTemplate.objects.get(
        id=form['id'],
    )

    operation_template.dttm_deleted = datetime.now()
    operation_template.save()

    return JsonResponse.success()


@api_method(
    'POST',
    UpdateOperationTemplateForm,
    lambda_func=lambda x: OperationTemplate.objects.get(id=x['id']).operation_type.work_type.shop
)
def update_operation_template(request, form):
    """
    Изменяет шаблон операции

    Args:
        method: POST
        url: /api/operation_template/update_operation_template
        'id': id шаблона,
        'name': название,
        'tm_start': время начала работ,
        'tm_end': время окончания работ,
        'value': количество человек,
        'period': ежедневно, неделя, месяц,
        'days_in_period': массив с номерами дней в неделе или месяце,
        'date_rebuild_from': дата с которой надо изменить расписание. Если не задана,
            построенное расписание меняться не будет

    Returns:
        {
            | 'id': id шаблона,
            | 'name': название,
            | 'tm_start': время начала работ,
            | 'tm_end': время окончания работ,
            | 'value': количество человек,
            | 'period': ежедневно, неделя, месяц,
            | 'days_in_period': массив с номерами дней в неделе или месяце,
            | 'operation_type_id': id типа операции,
            | 'dttm_added': ,
            | 'dttm_deleted': ,
        }

    Raises:
        JsonResponse.does_not_exists_error: если тип кассы с from/to_operation_type_id не существует\
        или если кассы с заданным номером и привязанной к данному типу не существует
        JsonResponse.multiple_objects_returned: если вернулось несколько объектов в QuerySet'e
    """

    id = form.pop('id')
    date_rebuild_from=form.pop('date_rebuild_from')

    try:
        operation_template = OperationTemplate.objects.get(
            id=id
            )
    except OperationTemplate.DoesNotExist:
        return JsonResponse.does_not_exists_error('operation template does not exist')

    build_period = False
    if operation_template.dt_built_to \
        and (operation_template.value != form['value'] \
             or operation_template.period != form['period'] \
             or operation_template.days_in_period != form['days_in_period']):
        build_period_clients(operation_template,
                              dt_from=form['date_rebuild_from'], operation='delete')

        build_period = True


    operation_template = OperationTemplateForm(form, instance=operation_template).save()

    if build_period:
        build_period_clients(operation_template,
                             dt_from=date_rebuild_from)
    return JsonResponse.success(
        OperationTemplateConverter.convert(operation_template)
    )
