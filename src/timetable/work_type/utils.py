import datetime

import numpy as np
from django.db.models import Q, F

from src.base.models import (
    Shop,
    ProductionDay,
    Employment,
)
from src.forecast.models import (
    PeriodClients,
)
from src.timetable.models import (
    WorkerDay,
    WorkType,
)
from src.util.models_converter import Converter


def get_efficiency(shop_id, form, consider_vacancies=False,):
    def dttm2index(dt_init, dttm, period_in_day, period_lengths_minutes):
        days = (dttm.date() - dt_init).days
        return days * period_in_day + (dttm.hour * 60 + dttm.minute) // period_lengths_minutes

    def fill_array(array, db_list, lambda_get_indexes, lambda_add):
        arr_sz = array.size
        for db_model in db_list:
            # период может быть до 12 ночи, а смена с 10 до 8 утра следующего дня и поэтому выходим за границы
            indexes = [ind for ind in lambda_get_indexes(db_model) if ind < arr_sz]
            array[indexes] += lambda_add(db_model)

    MINUTES_IN_DAY = 24 * 60
    shop = Shop.objects.all().select_related('settings').get(id=shop_id)
    period_lengths_minutes = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
    period_in_day = MINUTES_IN_DAY // period_lengths_minutes

    absenteeism_coef = 1
    if shop.settings:
        absenteeism_coef += shop.settings.absenteeism / 100

    from_dt = form['from_dt']
    # To include last day in "x < to_dt" conds
    to_dt = form['to_dt'] + datetime.timedelta(days=1)

    dttms = [
        datetime.datetime.combine(from_dt + datetime.timedelta(days=day), datetime.time(
            hour=period * period_lengths_minutes // 60,
            minute=period * period_lengths_minutes % 60)
                                  )
        for day in range((to_dt - from_dt).days)
        for period in range(MINUTES_IN_DAY // period_lengths_minutes)
    ]

    predict_needs = np.zeros(len(dttms))
    finite_work = np.zeros(len(dttms))

    # check cashboxes
    work_types = WorkType.objects.filter(shop_id=shop_id).order_by('id')
    if 'work_type_ids' in form and len(form['work_type_ids']) > 0:
        work_types = work_types.filter(id__in=form['work_type_ids'])
        if work_types.count() != len(form['work_type_ids']):
            return 'bad work_type_ids'

    work_types = {
        wt.id: wt
        for wt in work_types
    }

    need_workers = PeriodClients.objects.annotate(
        need_workers=F('value'),
    ).select_related('operation_type').filter(
        dttm_forecast__gte=from_dt,
        dttm_forecast__lte=to_dt,
        operation_type__work_type_id__in=work_types.keys(),
        operation_type__dttm_deleted__isnull=True,
    )

    lambda_index_periodclients = lambda x: [dttm2index(from_dt, x.dttm_forecast, period_in_day, period_lengths_minutes)]
    lambda_add_periodclients = lambda x: x.need_workers

    fill_array(
        predict_needs,
        list(need_workers.filter(type=PeriodClients.LONG_FORECASE_TYPE)),
        lambda_index_periodclients,
        lambda_add_periodclients,
    )
    predict_needs = absenteeism_coef * predict_needs

    # query selecting cashbox_details
    status_list = list(WorkerDay.TYPES_PAID)

    base_wd_q = Q(
        Q(employment__dt_fired__gte=from_dt) &
        Q(dt__lte=F('employment__dt_fired')) |
        Q(employment__dt_fired__isnull=True),

        Q(employment__dt_hired__lte=to_dt) &
        Q(dt__gte=F('employment__dt_hired')) |
        Q(employment__dt_hired__isnull=True),
        dt__gte=from_dt,
        dt__lte=to_dt,
    )
    if not consider_vacancies:
        base_wd_q &= Q(worker__isnull=False)

    qs_for_covering = WorkerDay.objects.filter(base_wd_q)

    graph_type = form.get('graph_type', 'plan_approved')
    if graph_type == 'plan_edit':
        qs_for_covering = qs_for_covering.get_plan_edit()
    else:
        qs_for_covering = qs_for_covering.get_plan_approved()

    qs_for_covering = qs_for_covering.filter(
        type__in=status_list,
        worker_day_details__work_type_id__in=work_types.keys(),
    ).annotate(work_part=F('worker_day_details__work_part')).distinct()

    lambda_index_work_days = lambda x: list(range(
        dttm2index(from_dt, x.dttm_work_start, period_in_day, period_lengths_minutes),
        dttm2index(from_dt, x.dttm_work_end, period_in_day, period_lengths_minutes),
    ))
    lambda_add_work_details = lambda x: x.work_part
    worker_days_list = list(qs_for_covering)

    finite_workdays = worker_days_list
    fill_array(
        finite_work,
        finite_workdays,
        lambda_index_work_days,
        lambda_add_work_details,
    )

    response = {}

    if form.get('efficiency', True):
        day_stats = {}
        graph_arr = finite_work

        dts_for_day_stats = [
            from_dt + datetime.timedelta(days=day)
            for day in range((to_dt - from_dt).days)
        ]

        graph_arr_daily = graph_arr.reshape(len(dts_for_day_stats), period_in_day)
        predict_needs_daily = predict_needs.reshape(len(dts_for_day_stats), period_in_day)
        for i, dt in enumerate(dts_for_day_stats):
            dt_converted = Converter.convert_date(dt)

            graph_arr_for_dt = graph_arr_daily[i]
            predict_needs_for_dt = predict_needs_daily[i]

            covering = np.nan_to_num(np.minimum(predict_needs_for_dt, graph_arr_for_dt).sum() / predict_needs_for_dt.sum())
            deadtime = np.nan_to_num(np.maximum(graph_arr_for_dt - predict_needs_for_dt, 0).sum() / graph_arr_for_dt.sum())
            predict_hours = predict_needs_for_dt.sum()
            graph_hours = graph_arr_for_dt.sum()

            day_stats.setdefault('covering', {})[dt_converted] = covering
            day_stats.setdefault('deadtime', {})[dt_converted] = deadtime
            day_stats.setdefault('predict_hours', {})[dt_converted] = predict_hours
            day_stats.setdefault('graph_hours', {})[dt_converted] = graph_hours

        real_cashiers = []
        predict_cashier_needs = []
        lack_of_cashiers_on_period = []
        for index, dttm in enumerate(dttms):
            dttm_converted = Converter.convert_datetime(dttm)
            real_cashiers.append({'dttm': dttm_converted, 'amount': finite_work[index]})
            predict_cashier_needs.append({'dttm': dttm_converted, 'amount': predict_needs[index]})
            lack_of_cashiers_on_period.append({
                'dttm': dttm_converted,
                'lack_of_cashiers': max(0, predict_needs[index] - finite_work[index])
            })

        response.update({
            'period_step': period_lengths_minutes,
            'tt_periods': {
                'real_cashiers': real_cashiers,
                'predict_cashier_needs': predict_cashier_needs,
            },
            'day_stats': day_stats,
            'lack_of_cashiers_on_period': lack_of_cashiers_on_period
        })

    if form.get('indicators', False):
        norm_work_hours = ProductionDay.get_norm_work_hours(shop.region_id, from_dt.month, from_dt.year)

        # TODO: если сотрудник уволен раньше to_dt, то будет некорректное значение?
        active_empls_norm_work_hours = sum(Employment.objects.filter(
            Q(dt_hired__lte=to_dt) | Q(dt_hired__isnull=True),
            Q(dt_fired__gte=from_dt) | Q(dt_fired__isnull=True),
            shop=shop,
        ).values_list('norm_work_hours', flat=True)) / 100
        # ФОТ считаем пока как: часы производственные календарь * кол-во сотрудников в штате с учетом их ставок.
        fot = norm_work_hours * active_empls_norm_work_hours
        covering = round(100 * np.nan_to_num(np.minimum(predict_needs, finite_work).sum() / predict_needs.sum()), 1)
        deadtime = round(100 * np.nan_to_num(np.maximum(finite_work - predict_needs, 0).sum() / (finite_work.sum())), 1)

        response.update({
            'indicators': {
                'deadtime': deadtime,
                'covering': covering,
                'fot': fot,
                'predict_needs': predict_needs.sum(),
            },
        })

    return response
