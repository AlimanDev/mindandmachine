from src.util.utils import api_method
from .utils import xlsx_method
from .forms import GetTable
from src.db.models import (
    Shop,
    User,
    WorkerDay,
)

from .xlsx.tabel import Tabel_xlsx
from src.util.forms import FormUtil
import json


@api_method('GET', GetTable)
@xlsx_method
def get_tabel(request, workbook, form):
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
