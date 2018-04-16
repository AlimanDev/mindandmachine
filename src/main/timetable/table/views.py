from src.db.models import User, WorkerCashboxInfo
from src.util.utils import api_method
from .forms import SelectCashiersForm


@api_method('GET', SelectCashiersForm)
def select_cashiers(request, form):
    shop_id = request.user.shop_id

    users = {x.id: x for x in User.objects.filter(shop_id=shop_id)}

    cashboxes_type_ids = set(form['cashbox_types'])
    if len(cashboxes_type_ids) > 0:
        users_hits = set()
        for x in WorkerCashboxInfo.objects.select_related('cashbox_type').filter(cashbox_type__shop_id=shop_id, is_active=True):
            if x.cashbox_type_id in cashboxes_type_ids:
                users_hits.add(x.worker_id)

        users = {x.id: x for x in users if x.id in users_hits}

    cashier_ids = set(form['cashier_ids'])
    if len(cashier_ids) > 0:
        users = {x.id: x for x in users if x.id in cashier_ids}

    work_types = set(form['work_types'])
    if len(work_types) > 0:
        pass
