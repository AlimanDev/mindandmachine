import datetime
from django.db.models import Avg, Sum, Q
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from src.db.models import Timetable, SuperShop
from dateutil.relativedelta import relativedelta
from src.util.models_converter import SuperShopConverter
from math import ceil


def calculate_supershop_stats(month, shop_ids):
    """

    :param month: eg. 01.02.2019
    :param shops:
    :return:
    """
    if not isinstance(shop_ids, QuerySet):
        shop_ids = [shop_ids]
    return Timetable.objects.filter(
        dt=month,
        shop__id__in=shop_ids
    ).aggregate(
        revenue=Coalesce(Sum('revenue'), 0),
        fot=Coalesce(Sum('fot'), 0),
        lack=Coalesce(Avg('lack'), 0),
        idle=Coalesce(Avg('idle'), 0),
        workers_amount=Coalesce(Sum('workers_amount'), 0),
        fot_revenue=Coalesce(Avg('fot_revenue'), 0),
    )


def get_super_shop_list_stats(form, display_format='raw'):
    dt_now = datetime.datetime.today().replace(day=1)
    dt_prev = dt_now - relativedelta(months=1)
    pointer = form['pointer']
    amount = form['items_per_page']
    sort_type = form['sort_type']
    filter_dict = {
        'title__icontains': form['title'],
        'type': form['super_shop_type'],
        'region__title': form['region'],
        'dt_opened__gte': form['opened_after_dt'],
        'dt_closed__lte': form['closed_before_dt'],
    }
    filter_dict = {k: v for k, v in filter_dict.items() if v}

    super_shops = SuperShop.objects.select_related('region').filter(**filter_dict)

    filter_dict = dict()

    range_filters = ['revenue', 'lack', 'fot', 'idle', 'workers_amount', 'fot_revenue']
    for range_filter in range_filters:
        tuple_values = form[range_filter]
        if tuple_values[0] is not None:
            filter_dict.update({range_filter + '_curr__gte': tuple_values[1]})
        if tuple_values[1] is not None:
            filter_dict.update({range_filter + '_curr__lte': tuple_values[0]})

    def calculate(func, field, period):
        return Coalesce(func('shop__timetable__' + field, filter=Q(shop__timetable__dt=period)), 0)

    super_shops = super_shops.prefetch_related('shop_set', 'shop_set__timetable_set').filter(
        Q(shop__timetable__dt__range=(dt_prev, dt_now)) | Q(shop__timetable__dt__isnull=True), # todo: actually needs to add condition Q(shop__timetable__dt__range=(dt_prev, dt_now)) to left join, not for where
        shop__dttm_deleted__isnull=True,
    ).annotate(
        workers_amount_curr=calculate(Sum, 'workers_amount', dt_now),
        workers_amount_prev=calculate(Sum, 'workers_amount', dt_prev),
        lack_curr=calculate(Avg, 'lack', dt_now),
        lack_prev=calculate(Avg, 'lack', dt_prev),
        idle_curr=calculate(Avg, 'idle', dt_now),
        idle_prev=calculate(Avg, 'idle', dt_prev),
        fot_curr=calculate(Sum, 'fot', dt_now),
        fot_prev=calculate(Sum, 'fot', dt_prev),
        revenue_curr=calculate(Sum, 'revenue', dt_now),
        revenue_prev=calculate(Sum, 'revenue', dt_prev),
        fot_revenue_curr=calculate(Avg, 'fot_revenue', dt_now),
        fot_revenue_prev=calculate(Avg, 'fot_revenue', dt_prev)
    ).filter(**filter_dict)

    if sort_type:
        super_shops = super_shops.order_by(sort_type + '_curr')

    total = super_shops.count()
    if display_format == 'raw':
        super_shops = super_shops[amount * pointer:amount * (pointer + 1)]
    return_list = []
    dynamic_values = dict()

    reverse_plus_fields = ['lack', 'idle', 'fot', 'fot_revenue']

    def change_sign(value, key):
        return value * (-1) if key in reverse_plus_fields else value

    for ss in super_shops:
        converted_ss = SuperShopConverter.convert(ss)
        #  откидываем лишние данные типа title, tm_start, tm_end, ...
        ss_dynamic_values = {k: v for k, v in ss.__dict__.items() if 'curr' in k or 'prev' in k}
        for key in range_filters:
            if key in [k[:-5] for k in ss_dynamic_values.keys()]:  # откидываем _curr, _prev
                curr_stats = ss_dynamic_values[key + '_curr']
                prev_stats = ss_dynamic_values[key + '_prev']
                dynamic_values[key] = {
                    'prev': prev_stats,
                    'curr': curr_stats,
                    'change': change_sign(
                        ceil((curr_stats / prev_stats - 1) * 100) if prev_stats else 0,
                        key
                    )
                }

        converted_ss.update(dynamic_values)
        return_list.append(converted_ss)

    return return_list, total
