from datetime import datetime, timedelta, time

from src.db.models import Shop
from src.util.collection import range_u
from src.util.models_converter import BaseConverter, PeriodDemandConverter, PeriodDemandChangeLogConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetCashboxesInfo


@api_method('GET', GetCashboxesInfo)
def get_cashboxes_info(request, form):
    shop = Shop.objects.get(id=form['shop_id'])

