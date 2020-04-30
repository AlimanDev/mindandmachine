import datetime
import numpy as np
from decimal import Decimal


from django.db.models import Q, F, Case, When, Sum, Value, IntegerField


from src.base.models import (
    Employment,
    Shop,
    ProductionDay,
)
from src.timetable.models import (
    WorkerDay,
    WorkType,
    WorkerDayCashboxDetails,
)
from src.forecast.models import (
    PeriodClients,
)
from src.util.models_converter import Converter
from src.main.urv.utils import wd_stat_count_total, wd_stat_count


def get_efficiency(shop_id, form, indicators_only=False, consider_vacancies=False):
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
    shop = Shop.objects.get(id=shop_id)
    period_lengths_minutes = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
    period_in_day = MINUTES_IN_DAY // period_lengths_minutes
    absenteeism_coef = 1 + shop.settings.absenteeism / 100

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
    fact_needs = np.zeros(len(dttms))
    init_work = np.zeros(len(dttms))
    finite_work = np.zeros(len(dttms))

    # check cashboxes
    work_types = WorkType.objects.filter(shop_id=shop_id).order_by('id')
    if 'work_type_ids' in form and len(form['work_type_ids']) > 0:
        work_types = work_types.filter(id__in=form['work_type_ids'])
        if len(work_types) != len(form['work_type_ids']):
            return 'bad work_type_ids'
    work_types = {
        wt.id: wt
        for wt in work_types
    }
    #work_types = group_by(work_types, group_key=lambda x: x.id)
    # query selecting PeriodClients
    need_workers = PeriodClients.objects.annotate(
        need_workers=F('value') / period_lengths_minutes,
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
        need_workers.filter(type=PeriodClients.LONG_FORECASE_TYPE),
        lambda_index_periodclients,
        lambda_add_periodclients,
    )
    predict_needs = absenteeism_coef * predict_needs

    fill_array(
        fact_needs,
        need_workers.filter(type=PeriodClients.FACT_TYPE),
        lambda_index_periodclients,
        lambda_add_periodclients,
    )

    # query selecting cashbox_details
    status_list = list(WorkerDayCashboxDetails.WORK_TYPES_LIST)
    if consider_vacancies:
        status_list.append(WorkerDayCashboxDetails.TYPE_VACANCY)

    cashbox_details = WorkerDayCashboxDetails.objects.filter(
        Q(worker_day__employment__dt_fired__gte=from_dt) &
        Q(dttm_to__lte=F('worker_day__employment__dt_fired')) |
        Q(worker_day__employment__dt_fired__isnull=True),

        Q(worker_day__employment__dt_hired__lte=to_dt) &
        Q(dttm_from__gte = F('worker_day__employment__dt_hired')) |
        Q(worker_day__employment__dt_hired__isnull=True),

        dttm_from__gte=from_dt,
        dttm_to__lte=to_dt,
        work_type_id__in=work_types.keys(),
        status__in=status_list
    ).select_related('worker_day', 'worker_day__worker')

    lambda_index_work_details = lambda x: list(range(
            dttm2index(from_dt, x.dttm_from, period_in_day, period_lengths_minutes),
            dttm2index(from_dt, x.dttm_to, period_in_day, period_lengths_minutes),
        ))
    lambda_add_work_details = lambda x: 1

    fill_array(
        init_work,
        cashbox_details.filter(worker_day__parent_worker_day__isnull=True),
        lambda_index_work_details,
        lambda_add_work_details,
    )

    employments = Employment.objects.filter(id__in=cashbox_details.values_list('worker_day__employment'))
    employment_dict= {e.id: e for e in employments}

    worker_days = WorkerDay.objects.qos_filter_version(1).filter(
        dt__gte=from_dt,
        dt__lte=to_dt,
        employment__in=employments,
        # employment__shop_id=shop_id,
        type=WorkerDay.TYPE_WORKDAY
    )

    hours_stat = wd_stat_count(worker_days, shop)
    fot = 0
    norm_work_hours = ProductionDay.objects.filter(
            dt__month=from_dt.month,
            dt__year=from_dt.year,
            type__in=ProductionDay.WORK_TYPES,
            region_id=shop.region_id,
        ).annotate(
            work_hours=Case(
                When(type=ProductionDay.TYPE_WORK, then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK])),
                When(type=ProductionDay.TYPE_SHORT_WORK, then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_SHORT_WORK])),
            )
        ).aggregate(
            norm_work_hours=Sum('work_hours', output_field=IntegerField())
        )['norm_work_hours']
    for row in hours_stat:
        fot += round(
            Decimal(row['hours_plan']) *
            employment_dict[row['employment_id']].salary / Decimal(norm_work_hours)
        )

    finite_workdetails = list(cashbox_details.filter(worker_day__child__id__isnull=True).select_related('worker_day'))
    fill_array(
        finite_work,
        finite_workdetails,
        lambda_index_work_details,
        lambda_add_work_details,
    )

    response = {}

    if not indicators_only:
        real_cashiers = []
        real_cashiers_initial = []
        fact_cashier_needs = []
        predict_cashier_needs = []
        lack_of_cashiers_on_period = []
        for index, dttm in enumerate(dttms):
            dttm_converted = Converter.convert_datetime(dttm)
            real_cashiers.append({'dttm': dttm_converted, 'amount': finite_work[index]})
            real_cashiers_initial.append({'dttm': dttm_converted,'amount': init_work[index]})
            fact_cashier_needs.append({'dttm': dttm_converted, 'amount': fact_needs[index]})
            predict_cashier_needs.append({'dttm': dttm_converted, 'amount': predict_needs[index]})
            lack_of_cashiers_on_period.append({
                'dttm': dttm_converted,
                'lack_of_cashiers': max(0,  predict_needs[index] - finite_work[index])
            })
        response = {
            'period_step': period_lengths_minutes,
            'tt_periods': {
                'real_cashiers': real_cashiers,
                'real_cashiers_initial': real_cashiers_initial,
                'predict_cashier_needs': predict_cashier_needs,
                'fact_cashier_needs': fact_cashier_needs,
            },
            'lack_of_cashiers_on_period': lack_of_cashiers_on_period
        }

    # statistics
    worker_amount = len(set([x.worker_day.worker_id for x in finite_workdetails if x.worker_day]))
    deadtime_part = round(100 * np.maximum(finite_work - predict_needs, 0).sum() / (finite_work.sum() +1e-8), 1)
    covering_part = round(100 * np.maximum(predict_needs - finite_work, 0).sum() / (predict_needs.sum() +1e-8), 1)
    days_diff = (predict_needs - finite_work).reshape(period_in_day, -1).sum(1) / (period_in_day / 3) # in workers
    need_cashier_amount = np.maximum(days_diff[np.argsort(days_diff)[-1:]], 0).sum() # todo: redo with logic

    revenue = 1000000

    response.update({
        'indicators': {
            'deadtime_part': deadtime_part,
            'cashier_amount': worker_amount,  # len(users_amount_set),
            'FOT': fot if fot else None,
            'need_cashier_amount': need_cashier_amount,  # * 1.4
            'revenue': revenue,
            'fot_revenue': round(fot / revenue, 2) * 100,
            # 'change_amount': changed_amount,
            'covering_part': covering_part,

            'total_need': predict_needs.sum(),
            'total_go': finite_work.sum(),
            'total_plan': shop.staff_number * norm_work_hours,
            'hours_count_fact': wd_stat_count_total(worker_days, shop)['hours_count_fact'],
        },
    })
    return response
