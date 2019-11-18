import datetime
from django.db.models import (
    Avg, Sum,
    FloatField, IntegerField,
    Subquery, OuterRef
    )
from django.db.models.functions import Coalesce
from src.db.models import (
    Employment,
    Shop,
    Timetable,
)
from dateutil.relativedelta import relativedelta
from src.util.models_converter import ShopConverter
from math import ceil


class SubAggr(Subquery):
    def __init__(self, qs, func, field, field_type, *args, **extra):
        self.template = f"(SELECT {func}({field}) FROM (%(subquery)s) _count)"
        self.output_field = field_type
        super(SubAggr, self).__init__(qs, *args, **extra)

def calculate_supershop_stats(month, shop_ids):
    """

    :param month: eg. 01.02.2019
    :param shops:
    :return:
    """
    # if not isinstance(shop_ids, QuerySet):
    #     shop_ids = [shop_ids]
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


def get_shop_list_stats(form, request, display_format='raw'):
    pointer = form['pointer']
    amount = form['items_per_page']
    sort_type = form['sort_type']
    filter_dict = {
        'title__icontains': form['title'],
        'dt_opened__gte': form['opened_after_dt'],
        'dt_closed__lte': form['closed_before_dt'],
    }

    filter_dict = {k: v for k, v in filter_dict.items() if v}

    range_filters = ['revenue', 'lack', 'fot', 'idle', 'workers_amount', 'fot_revenue']
    for range_filter in range_filters:
        tuple_values = form[range_filter]
        if tuple_values[0] is not None:
            filter_dict.update({range_filter + '_curr__gte': tuple_values[1]})
        if tuple_values[1] is not None:
            filter_dict.update({range_filter + '_curr__lte': tuple_values[0]})


    dt_curr = datetime.datetime.today().replace(day=1)
    dt_prev = dt_curr - relativedelta(months=1)

    childs_subquery_curr = Shop.objects.filter(
        dttm_deleted__isnull=True,
        lft__gte=OuterRef('lft'),
        lft__lte=OuterRef('rght'),
        tree_id=OuterRef('tree_id'),
        timetable__dt=dt_curr
    ).order_by().values(
        'timetable__fot',
        'timetable__fot_revenue',
        'timetable__revenue',
        'timetable__lack',
        'timetable__idle',
        'timetable__workers_amount'
    )

    childs_subquery_prev = Shop.objects.filter(
        dttm_deleted__isnull=True,
        lft__gte=OuterRef('lft'),
        lft__lte=OuterRef('rght'),
        tree_id=OuterRef('tree_id'),
        timetable__dt=dt_prev
    ).order_by().values(
        'timetable__fot',
        'timetable__fot_revenue',
        'timetable__revenue',
        'timetable__lack',
        'timetable__idle',
        'timetable__workers_amount'
    )


    if request.shop:
        shops = request.shop.get_children()
    else:
        shop_ids = Employment.objects.get_active(dt_curr, dt_curr).filter(
            user=request.user,
        ).values_list('shop_id', flat=True)

        shops = Shop.objects.filter(id__in=shop_ids)
        if len(shops)==1:
            shops = shops[0].get_children()

    shops=shops.filter(
            dttm_deleted__isnull=True,
            **filter_dict
        )

    total = shops.count()

    shops=shops.annotate(
        fot_prev=SubAggr(childs_subquery_prev, func='sum', field='fot', field_type=FloatField()),
        fot_curr=SubAggr(childs_subquery_curr, func='sum', field='fot', field_type=FloatField()),

        fot_revenue_prev=SubAggr(childs_subquery_prev, func='avg', field='fot_revenue', field_type=FloatField()),
        fot_revenue_curr=SubAggr(childs_subquery_curr, func='avg', field='fot_revenue', field_type=FloatField()),

        lack_prev=SubAggr(childs_subquery_prev, func='avg', field='lack', field_type=FloatField()),
        lack_curr=SubAggr(childs_subquery_curr, func='avg', field='lack', field_type=FloatField()),

        idle_prev=SubAggr(childs_subquery_prev, func='avg', field='idle', field_type=FloatField()),
        idle_curr=SubAggr(childs_subquery_curr, func='avg', field='idle', field_type=FloatField()),

        workers_amount_prev=SubAggr(childs_subquery_prev, func='sum', field='workers_amount', field_type=IntegerField()),
        workers_amount_curr=SubAggr(childs_subquery_curr, func='sum', field='workers_amount', field_type=IntegerField()),

        revenue_prev=SubAggr(childs_subquery_prev, func='sum', field='revenue', field_type=IntegerField()),
        revenue_curr=SubAggr(childs_subquery_curr, func='sum', field='revenue', field_type=IntegerField()),
    ).order_by('id')

    if sort_type:
        shops = shops.order_by(sort_type + '_curr' if 'title' not in sort_type else sort_type)

    if display_format == 'raw':
        shops = shops[amount * pointer:amount * (pointer + 1)]
    return_list = []
    dynamic_values = dict()

    reverse_plus_fields = ['lack', 'idle', 'fot', 'fot_revenue']

    def change_sign(value, key):
        return value * (-1) if key in reverse_plus_fields else value

    for ss in shops:
        converted_ss = ShopConverter.convert(ss)
        #  откидываем лишние данные типа title, tm_start, tm_end, ...
        ss_dynamic_values = {k: v for k, v in ss.__dict__.items() if 'curr' in k or 'prev' in k}
        for key in range_filters:
            if key in [k[:-5] for k in ss_dynamic_values.keys()]:  # откидываем _curr, _prev
                curr_stats = ss_dynamic_values[key + '_curr']
                prev_stats = ss_dynamic_values[key + '_prev']
                dynamic_values[key] = {
                    'prev': prev_stats if prev_stats else 0,
                    'curr': curr_stats if curr_stats else 0,
                    'change': change_sign(
                        ceil((curr_stats / prev_stats - 1) * 100) if (prev_stats and curr_stats) else 0,
                        key
                    )
                }

        converted_ss.update(dynamic_values)
        return_list.append(converted_ss)

    return return_list, total
