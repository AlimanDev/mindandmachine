from openpyxl import load_workbook
import datetime

from src.util.utils import api_method, JsonResponse
from .utils import xlsx_method
from .forms import GetTable
from src.db.models import (
    Shop,
    User
)

from .xlsx.tabel import Tabel_xlsx


@api_method('GET', GetTable)
@xlsx_method
def get_tabel(request, workbook, form):
    ws = workbook.add_worksheet(Tabel_xlsx.MONTH_NAMES[form['weekday'].month])

    shop = Shop.objects.get(id=form['shop_id'])
    tabel = Tabel_xlsx(
        workbook,
        shop,
        form['weekday'],
        worksheet=ws,
        prod_days=None
    )
    tabel.add_main_info()

    # construct day
    tabel.construct_dates('%d', 13, 5, int)

    # construct weekday
    tabel.construct_dates('%w', 17, 5)

    #construct day 2
    tabel.construct_dates('d%d', 20, 5)

    users = User.objects.qos_filter_active(
        dt_from=tabel.prod_days[-1].dt,
        dt_to=tabel.prod_days[0].dt,
        shop=shop,
    ).select_related('position').order_by('position_id')

    tabel.construnts_users_info(users, 17, 0, ['code', 'fio', 'position', 'hired'])

    # tabel.add_sign(20)

    return workbook, 'Tabel'
