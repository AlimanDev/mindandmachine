from src.util.utils import api_method
from .utils import xlsx_method
from .forms import GetTable, GetDemandXlsxForm
from src.db.models import (
    Shop,
    User,
    WorkerDay,
    PeriodClients,
)
from django.apps import apps
from src.util.utils import JsonResponse

from .xlsx.tabel import Tabel_xlsx
from src.util.forms import FormUtil
import json


@api_method('GET', GetTable)
@xlsx_method
def get_tabel(request, workbook, form):
    """
    Скачать табель на дату

    Args:
        method: GET
        url: api/download/get_tabel
        shop_id(int): required = False
        weekday(QOS_DATE): на какую дату табель хотим
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        Табель
    """
    ws = workbook.add_worksheet(Tabel_xlsx.MONTH_NAMES[form['weekday'].month])

    shop = Shop.objects.get(id=FormUtil.get_shop_id(request, form))
    checkpoint = FormUtil.get_checkpoint(form)

    tabel = Tabel_xlsx(
        workbook,
        shop,
        form['weekday'],
        worksheet=ws,
        prod_days=None
    )
    users = list(User.objects.qos_filter_active(
        dt_from=tabel.prod_days[-1].dt,
        dt_to=tabel.prod_days[0].dt,
        shop=shop,
    ).select_related('position').order_by('position_id', 'last_name', 'first_name', 'tabel_code'))

    breaktimes = json.loads(shop.break_triplets)
    breaktimes = list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), breaktimes))

    workdays = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
        worker__shop=shop,
        dt__gte=tabel.prod_days[0].dt,
        dt__lte=tabel.prod_days[-1].dt,
    ).order_by('worker__position_id', 'worker__last_name', 'worker__first_name', 'worker__tabel_code', 'dt')

    tabel.format_cells(len(users))
    tabel.add_main_info()

    # construct day
    tabel.construct_dates('%d', 12, 6, int)

    # construct weekday
    tabel.construct_dates('%w', 14, 6)

    #construct day 2
    tabel.construct_dates('d%d', 15, 6)

    tabel.construnts_users_info(users, 16, 0, ['code', 'fio', 'position', 'hired'])

    tabel.fill_table(workdays, users, breaktimes, 16, 6)

    tabel.add_xlsx_functions(len(users), 12, 37)
    tabel.add_sign(16 + len(users) + 2)

    return workbook, 'Tabel'


@api_method(
    'GET',
    GetDemandXlsxForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
@xlsx_method
def get_demand_xlsx(request, workbook, form):
    """
    Скачивает спрос по "клиентам" в эксель формате

    Args:
        method: GET
        url: /api/demand/get_clients_xlsx
        from_dt(QOS_DATE): с какой даты скачивать
        to_dt(QOS_DATE): по какую дату скачивать
        shop_id(int): в каком магазине
        demand_model(char): !! attention !! передавать что-то из clients/queue/products (см. окончание моделей Period..)

    Returns:
        эксель файл с форматом Тип работ | Время | Значение
    """
    def filter_over_model(model):
        filter_dict = {
            'cashbox_type__shop_id': form['shop_id'],
            'dttm_forecast__date__gte': from_dt,
            'dttm_forecast__date__lte': to_dt,
        }
        period_demands = model.objects.filter(
            type=PeriodClients.LONG_FORECASE_TYPE,
            **filter_dict
        )
        period_demands_fact = model.objects.filter(
            type=PeriodClients.FACT_TYPE,
            **filter_dict
        )
        return period_demands, period_demands_fact

    from_dt = form['from_dt']
    to_dt = form['to_dt']

    worksheet = workbook.add_worksheet('{}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d')))
    worksheet.write(0, 0, 'Тип работ')
    worksheet.write(0, 1, 'Время')
    worksheet.write(0, 2, 'Значение(долгосрочный)')
    worksheet.write(0, 3, 'Значение(фактический)')

    try:
        model = apps.get_model('db', 'period{}'.format(form['demand_model']))
    except LookupError:
        return JsonResponse.internal_error('incorrect demand model')

    period_demands, period_demands_fact = filter_over_model(model)

    for index, forecast_item in enumerate(period_demands):
        fact_on_concrete_date = period_demands_fact.filter(
            dttm_forecast=forecast_item.dttm_forecast,
            cashbox_type=forecast_item.cashbox_type
        ).first()

        worksheet.write(index + 1, 0, forecast_item.cashbox_type.name)
        worksheet.write(index + 1, 1, forecast_item.dttm_forecast.strftime('%H:%M:%S'))
        worksheet.write(index + 1, 2, round(forecast_item.value, 1))
        worksheet.write(index + 1, 3, round(forecast_item.value, 1) if fact_on_concrete_date else 'Нет данных')

    return workbook, '{} {}-{}'.format(model.__name__, from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d'))