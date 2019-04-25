import datetime
from django.db.models import Avg, Sum, Q, Case, When, F, FloatField, Value, IntegerField
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from src.db.models import (
    Timetable,
    SuperShop,
    FunctionGroup,
)
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


def get_super_shop_list_stats(form, request, display_format='raw'):
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

    show_self = request.user.function_group.allowed_functions.filter(func='get_super_shop_list').first()
    if show_self is None:
        return [], 0
    if show_self.access_type == FunctionGroup.TYPE_ALL:
        pass
    elif show_self.access_type == FunctionGroup.TYPE_SUPERSHOP:
        filter_dict.update({
            'id': request.user.shop.super_shop_id
        })
    else:
        return [], 0

    filter_dict = {k: v for k, v in filter_dict.items() if v}

    range_filters = ['revenue', 'lack', 'fot', 'idle', 'workers_amount', 'fot_revenue']
    for range_filter in range_filters:
        tuple_values = form[range_filter]
        if tuple_values[0] is not None:
            filter_dict.update({range_filter + '_curr__gte': tuple_values[1]})
        if tuple_values[1] is not None:
            filter_dict.update({range_filter + '_curr__lte': tuple_values[0]})

    def aggr_constructor(func, field, field_type, **filter_kwargs):
        return func(Case(
            When(then=F(field), **filter_kwargs),
            default=Value(0),
            output_field=field_type(),
        ))

    st = 'shop__timetable__'  # short alias
    prev_filters = {st + 'dt': dt_prev}
    curr_filters = {st + 'dt': dt_now}

    super_shops = SuperShop.objects.select_related('region').annotate(
        workers_amount_prev=aggr_constructor(Sum, st + 'workers_amount', IntegerField, **prev_filters),
        lack_prev=aggr_constructor(Avg, st + 'lack', FloatField, **prev_filters),
        idle_prev=aggr_constructor(Avg, st + 'idle', FloatField, **prev_filters),
        fot_prev=aggr_constructor(Sum, st + 'fot', FloatField, **prev_filters),
        revenue_prev=aggr_constructor(Sum, st + 'revenue', FloatField, **prev_filters),
        fot_revenue_prev=aggr_constructor(Avg, st + 'fot_revenue', FloatField, **prev_filters),

        workers_amount_curr=aggr_constructor(Sum, st + 'workers_amount', IntegerField, **curr_filters),
        lack_curr=aggr_constructor(Avg, st + 'lack', FloatField, **curr_filters),
        idle_curr=aggr_constructor(Avg, st + 'idle', FloatField, **curr_filters),
        fot_curr=aggr_constructor(Sum, st + 'fot', FloatField, **curr_filters),
        revenue_curr=aggr_constructor(Sum, st + 'revenue', FloatField, **curr_filters),
        fot_revenue_curr=aggr_constructor(Avg, st + 'fot_revenue', FloatField, **curr_filters),
    ).filter(
        shop__dttm_deleted__isnull=True,
        **filter_dict
    )

    if sort_type:
        super_shops = super_shops.order_by(sort_type + '_curr' if 'title' not in sort_type else sort_type)

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
