"""
Note:
    Во всех функциях, которые ищут сотрудников для замены в качестве аргумента используется

    arguments_dict = {
        | 'shop_id': int,
        | 'dttm_exchange_start(datetime.datetime): дата-время, на которые искать замену,
        | 'dttm_exchange_end(datetime.datetime): дата-время, на которые искать замену,
        | 'work_type'(int): на какую специализацию ищем замену,
        | 'predict_demand'(list): QuerySet PeriodDemand'ов,
        | 'mean_bills_per_step'(dict): по ключу -- id типа кассы, по значению -- средняя скорость,
        | 'work_types_dict'(dict): по ключу -- id типа кассы, по значению -- объект
        | 'users_who_can_work(list): список пользователей, которые могут работать на ct_type
    }

    Если одна из функций падает, рейзим ValueError, во вьюхе это отлавливается, и возвращается в 'info' в какой \
    именно функции произошла ошибка.

    А возвращается:
        {
            user_id: {
                | 'type': ,
                | 'tm_start': ,
                | 'tm_end':
            }, ..
        }
"""
from datetime import date, timedelta, datetime
import pandas

from django.db.models import Q, Exists, OuterRef
from django.utils.timezone import now
from django.conf import settings

from src.main.timetable.cashier_demand.utils import get_worker_timetable2 as get_shop_stats
from src.db.models import (
    ExchangeSettings,
    WorkerDay,
    Event,
    User,
    WorkerDayCashboxDetails,
    Shop
)
from src.util.models_converter import BaseConverter
from src.conf.djconfig import (
    QOS_DATETIME_FORMAT,
)


def search_candidates(wd_details, **kwargs):
    """

    :param wd_details: db.WorkerDayCashboxDetails -- only in python, not real model in db. idea: no model until users selected for sending
    :param kwargs: dict {
        'outsource': Boolean, if True then show, добавляем аутсорс
    }
    :return:
    """

    exchange_settings = ExchangeSettings.objects.first()
    if not exchange_settings.automatic_worker_select_tree_level:
        return
    shop = wd_details.work_type.shop
    parent = shop.get_ancestor_by_level_distance(exchange_settings.automatic_worker_select_tree_level)
    shops = parent.get_descendants()

    # department checks

    depart_filter = Q(shop_id__in=shops)

    # todo: add outsource

    # todo: 1. add time gap for check if different shop
    # todo: 2. add WorkerCashboxInfo check if necessary
    # todo: 3. add Location check
    workers = User.objects.filter(
        depart_filter,
        dt_fired__isnull=True,
        is_ready_for_overworkings=True,
    ).annotate(
        no_wdays=~Exists(WorkerDay.objects.filter(
            worker=OuterRef('pk'),
            dttm_work_start__lte=wd.dttm_to,
            dttm_work_end__gte=wd.dttm_from,
            dt=wd.dttm_from.date(),
            ))
    ).filter(no_wdays=True)

    return workers


def send_noti2candidates(users, worker_day_detail):
    event = Event.objects.mm_event_create(
        users,
        push_title='Открыта вакансия на {}'.format(BaseConverter.convert_date(worker_day_detail.dttm_from.date())),

        text='',
        department_id=worker_day_detail.work_type.shop_id,
        workerday_details=worker_day_detail,
    )
    return event


def cancel_vacancy(vacancy_id):
    # todo: change user work day if selected
    WorkerDayCashboxDetails.objects.filter(id=vacancy_id, is_vacancy=True).update(
        dttm_deleted=now(),
        status=WorkerDayCashboxDetails.TYPE_DELETED,
    )


def confirm_vacancy(vacancy_id, user):
    """

    :param vacancy_id:
    :param user:
    :return:
    0 -- все ок
    1 -- нет открытой вакансии
    2 -- не может подтвердить с учетом графика (пересечение есть)
    """
    vacancy = WorkerDayCashboxDetails.objects.filter(
        id=vacancy_id,
        is_vacancy=True,
        dttm_deleted__isnull=True,
        worker_day__isnull=True,
    ).last()
    if vacancy is None:
        return 1


    workerday = WorkerDay.objects.qos_current_version().filter(
        dt=vacancy.dttm_from.date(),
        worker=user,
    ).last()

    # todo: add better time checker if not the same
    WorkerDayCashboxDetails.objects.filter(
        worker_day=workerday,

    )


def create_vacancies_and_notify(shop_id, work_type_id):
    """
    Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров

    """

    shop=Shop.objects.get(id=shop_id)
    exchange_settings = ExchangeSettings.objects.first()
    if not exchange_settings.automatic_check_lack:
        return
    dttm_now = now().replace(minute=0, second=0, microsecond=0)
    dttm_next_week = dttm_now + exchange_settings.automatic_check_lack_timegap
    params = {
        'from_dt': dttm_now.date(),
        'to_dt': dttm_next_week.date(),
    }

    print('check vacancies for {}; {}'.format(shop_id, work_type_id))
    params['work_type_ids'] = [work_type_id]
    shop_stat = get_shop_stats(
        shop_id,
        params,
        consider_vacancies=True)
    df_stat = pandas.DataFrame(shop_stat['lack_of_cashiers_on_period'])
    # df_stat['dttm'] = pandas.to_datetime(df_stat.dttm, format=QOS_DATETIME_FORMAT)
    #df_stat['lack_of_cashiers'] = round(df_stat['lack_of_cashiers'])
    #df_stat = df_stat.where(df_stat.lack_of_cashiers>0).dropna()

    vacancies = []
    need_vacancy = 0
    vacancy = None
    while len(df_stat.loc[df_stat.lack_of_cashiers>0]):
        for i in df_stat.index:
            if df_stat['lack_of_cashiers'][i] > 0:
                if need_vacancy == 0:
                    need_vacancy = 1
                    vacancy = { 'dttm_from': df_stat['dttm'][i], 'lack': 0, 'count': 0 }
                vacancy['lack'] += df_stat['lack_of_cashiers'][i] if df_stat['lack_of_cashiers'][i] < 1 else 1
                vacancy['count'] += 1
            else:
                if need_vacancy == 1:
                    need_vacancy = 0
                    vacancy['dttm_to'] = df_stat['dttm'][i]
                    vacancies.append(vacancy)
                    vacancy = None
        if vacancy:
            vacancy['dttm_to'] = df_stat.tail(1)['dttm'].iloc[0]
            vacancies.append(vacancy)
            vacancy = None
            need_vacancy = 0
        #df_stat = df_stat.where(df_stat>0).dropna()
        df_stat['lack_of_cashiers'] = df_stat['lack_of_cashiers'] - 1

        # unite vacancies
    if not vacancies:
        return

    df_vacancies = pandas.DataFrame(vacancies)
    df_vacancies['dttm_from'] = pandas.to_datetime(df_vacancies['dttm_from'], format=QOS_DATETIME_FORMAT)
    df_vacancies['dttm_to'] = pandas.to_datetime(df_vacancies['dttm_to'], format=QOS_DATETIME_FORMAT)
    df_vacancies['delta'] = df_vacancies['dttm_to'] - df_vacancies['dttm_from']
    df_vacancies['next_index'] = -1
    df_vacancies['next'] = -1
    df_vacancies = df_vacancies.sort_values(by=['dttm_from','dttm_to']).reset_index(drop=True)

    df_vacancies.lack = df_vacancies.lack / df_vacancies['count']
    df_vacancies = df_vacancies.loc[df_vacancies.lack>exchange_settings.automatic_create_vacancy_lack_min]
    for i in df_vacancies.index:
        next_row =  df_vacancies.loc[
            (df_vacancies.dttm_from < df_vacancies['dttm_to'][i] + timedelta(hours=4)) &
            (df_vacancies.dttm_from >  df_vacancies['dttm_to'][i])
        ].dttm_from

        if next_row.empty:
            continue
        print(next_row)

        df_vacancies.loc[i,'next_index'] = next_row.index[0]
        df_vacancies.loc[i,'next'] = next_row[next_row.index[0]] - df_vacancies.dttm_to[i]

    for i in df_vacancies.where(df_vacancies.next_index>-1).dropna().sort_values(by=['next']).index:
        if df_vacancies.next_index[i] not in df_vacancies.index:
            df_vacancies.loc[i,'next_index'] = -1
            continue
        next_index = df_vacancies.next_index[i]
        next_row = df_vacancies.loc[next_index]
        df_vacancies.loc[next_index, 'dttm_from'] = df_vacancies.dttm_from[i]
        df_vacancies.loc[next_index,'delta'] = df_vacancies.dttm_to[next_index] - df_vacancies.dttm_from[next_index]
        df_vacancies.drop([i], inplace=True)

    max_shift = exchange_settings.working_shift_max_hours
    min_shift = exchange_settings.working_shift_min_hours
    for i in df_vacancies.index:
        working_shifts = [df_vacancies.delta[i]]

        #TODO проверить покрытие нехватки вакансиями
        if df_vacancies.delta[i] > max_shift:
            rest = df_vacancies.delta[i] % max_shift
            count = int(df_vacancies.delta[i] / max_shift)

            if not rest:
                working_shifts = [max_shift] * count
            else:
                working_shifts = [max_shift] * (count-1)
                working_shifts.append(max_shift + rest - min_shift)
                working_shifts.append(min_shift)
        elif df_vacancies.delta[i] < min_shift / 2:
        #elif df_vacancies.delta[i] < exchange_settings.automatic_create_vacancy_lack_min:
            working_shifts = []
        elif df_vacancies.delta[i] < min_shift:
            working_shifts = [min_shift]
        dttm_to = dttm_from = df_vacancies.dttm_from[i]

        # TODO:
        # tm_shop_closes = 00:00?
        # tm_shop_opens

        dttm_shop_opens = datetime.combine(dttm_from.date(), shop.tm_shop_opens)
        dttm_shop_closes = datetime.combine(dttm_from.date(), shop.tm_shop_closes)
        if shop.tm_shop_closes == time(hour=0, minute=0, second=0):
            dttm_shop_closes += timedelta(days=1)

        for shift in working_shifts:
            dttm_from = dttm_to
            dttm_to = dttm_to + shift
            if dttm_to > dttm_shop_closes:
                dttm_to = dttm_shop_closes
                dttm_from = dttm_to - shift
            if dttm_from < dttm_shop_opens:
                dttm_from = dttm_shop_opens
            print('create vacancy {} {} {}'.format(dttm_from, dttm_to, work_type_id))

            worker_day_detail = WorkerDayCashboxDetails.objects.create(
                dttm_from=dttm_from,
                dttm_to=dttm_to,
                work_type_id=work_type_id,
                status=WorkerDayCashboxDetails.TYPE_VACANCY,
                is_vacancy=True,
            )

            workers = search_candidates(
                worker_day_detail,
                own_shop=True,
                other_shops=True,
                other_supershops=True,
                outsource=True)
            send_noti2candidates(workers, worker_day_detail)


def cancel_vacancies(shop_id, work_type_id):
    """
    Автоматически отменяем вакансии, в которых нет потребности
    :return:
    """
    exchange_settings = ExchangeSettings.objects.first()
    if not exchange_settings.automatic_check_lack:
        return

    from_dt = now().replace(minute=0, second=0, microsecond=0)
    to_dt = from_dt + exchange_settings.automatic_check_lack_timegap
    min_dttm = from_dt + exchange_settings.automatic_worker_select_timegap

    from_dt = from_dt.date()
    to_dt = to_dt.date()

    params = {
        'from_dt': from_dt,
        'to_dt': to_dt,
    }

    params['work_type_ids'] = [work_type_id]
    shop_stat = get_shop_stats(
        shop_id,
        params,
        consider_vacancies=True)
    df_stat=pandas.DataFrame(shop_stat['tt_periods']['real_cashiers']).rename({'amount':'real_cashiers'}, axis=1)
    df_stat['predict_cashier_needs'] = pandas.DataFrame(shop_stat['tt_periods']['predict_cashier_needs']).amount

    df_stat['overflow'] = df_stat.real_cashiers - df_stat.predict_cashier_needs
    df_stat['dttm'] = pandas.to_datetime(df_stat.dttm, format=QOS_DATETIME_FORMAT)
    df_stat.set_index(df_stat.dttm, inplace=True)

    work_types = list(WorkerDayCashboxDetails.WORK_TYPES_LIST)
    work_types.append(WorkerDayCashboxDetails.TYPE_VACANCY)

    vacancies = WorkerDayCashboxDetails.objects.filter(
        (Q(worker_day__worker__id__isnull=False) & Q(dttm_from__gte=min_dttm)) | Q(worker_day__worker__id__isnull=True),
        dttm_from__gte=from_dt,
        dttm_to__lte=to_dt,
        work_type_id__in=[work_type_id],
        is_vacancy=True,
        status__in=work_types,
    ).order_by('status','dttm_from','dttm_to')

    for vacancy in vacancies:
        cond = (df_stat['dttm'] >= vacancy.dttm_from) & (df_stat['dttm'] <= vacancy.dttm_to)
        overflow = df_stat.loc[cond,'overflow'].apply(lambda x:  x if (x < 1.0 and x >-1.0) else 1 if x >=1 else -1 ).mean()
        print ('vacancy {} overflow {}'.format(vacancy, overflow))
        lack = 1-overflow
        if lack < exchange_settings.automatic_delete_vacancy_lack_max:
            print ('cancel_vacancy overflow {} {} {}'.format(overflow, vacancy, vacancy.dttm_from))
            cancel_vacancy(vacancy.id)
            df_stat.loc[cond,'overflow'] -= 1


def workers_exchange():
    """
    Автоматически перекидываем сотрудников из других магазинов, если это приносит ценность (todo: добавить описание, что такое ценность).

    :return:
    """
    exchange_settings = ExchangeSettings.objects.first()
    if not exchange_settings.automatic_check_lack:
        return

    from_dt = (now().replace(minute=0, second=0, microsecond=0) + exchange_settings.automatic_worker_select_timegap).date()
    to_dt = from_dt + exchange_settings.automatic_check_lack_timegap
    params = {
        'from_dt': from_dt,
        'to_dt': to_dt,
    }

    shop_list = Shop.objects.all()
    df_shop_stat = pandas.DataFrame()

    for shop in shop_list:
        for work_type in shop.worktype_set.all():
            params['work_type_ids'] = [work_type.id]

            shop_stat = get_shop_stats(
                shop.id,
                params,
                consider_vacancies=False)

            df_stat=pandas.DataFrame(shop_stat['tt_periods']['real_cashiers']).rename({'amount':'real_cashiers'}, axis=1)
            df_stat['predict_cashier_needs'] = pandas.DataFrame(shop_stat['tt_periods']['predict_cashier_needs']).amount
            df_stat['lack'] = df_stat.predict_cashier_needs - df_stat.real_cashiers
            df_stat['dttm'] = pandas.to_datetime(df_stat.dttm, format=QOS_DATETIME_FORMAT)
            # df_stat['shop_id'] = shop.id
            df_stat['work_type_id'] = work_type.id
            df_shop_stat = df_shop_stat.append(df_stat)

    df_shop_stat.set_index([# df_shop_stat.shop_id,
                            df_shop_stat.work_type_id, df_shop_stat.dttm], inplace=True)

    for shop in shop_list:
        for work_type in shop.worktype_set.all():

            vacancies = WorkerDayCashboxDetails.objects.filter(
                dttm_from__gte=from_dt,
                dttm_to__lte=to_dt,
                work_type_id=work_type.id,
                is_vacancy=True,
                status=WorkerDayCashboxDetails.TYPE_VACANCY
            ).order_by('status','dttm_from','dttm_to')

            for vacancy in vacancies:
                vacancy_lack = _lack_calc( df_shop_stat, work_type.id, vacancy.dttm_from, vacancy.dttm_to)
                print ('lack: {}; vacancy: {}; work_type: {}'.format(vacancy_lack, vacancy, work_type))
                dttm_from_workers = vacancy.dttm_from - timedelta(hours=4)
                if vacancy_lack > 0:
                    wd_details = WorkerDayCashboxDetails.objects.filter(
                        dttm_from=vacancy.dttm_from,
                        dttm_to=vacancy.dttm_to,
                        # work_type_id__in=[1],
                        is_vacancy=False,
                        status__in=WorkerDayCashboxDetails.WORK_TYPES_LIST,
                    ).exclude(
                        work_type_id=work_type.id,
                    ).order_by('status','dttm_from','dttm_to')
                    if not len(wd_details):
                        continue
                    worker_lack = None
                    candidate_to_change = None
                    for wd_detail in wd_details:
                        lack = _lack_calc(df_shop_stat, wd_detail.work_type_id, wd_detail.dttm_from, wd_detail.dttm_to )
                        if worker_lack is None or lack < worker_lack:
                            worker_lack = lack
                            candidate_to_change = wd_detail
                    print ('worker lack: {}; wd_detail: {}; work type: {}'.format(worker_lack, wd_detail, wd_detail.work_type))

                    if  worker_lack < -exchange_settings.automatic_worker_select_overflow_min:
                        user = candidate_to_change.worker_day.worker
                        print('hard exchange date {} worker_lack {} vacancy_lack {} shop_to {} shop_from {} candidate_to_change {} to vac {} user {}'.format(
                            vacancy.dttm_from, worker_lack, vacancy_lack,
                            work_type, candidate_to_change.work_type,
                            candidate_to_change, vacancy, user
                        ))
                        candidate_to_change.delete()
                        event = Event.objects.get(workerday_details=vacancy.id)
                        event.do_action(user)

                        _lack_add(df_shop_stat, work_type.id, vacancy.dttm_from, vacancy.dttm_to, -1 )
                        _lack_add(df_shop_stat, candidate_to_change.work_type_id, candidate_to_change.dttm_from, candidate_to_change.dttm_to, 1 )


def _lack_add(df, work_type_id, dttm_from, dttm_to, add):
    cond = (df.work_type_id==work_type_id) & (df['dttm'] >= dttm_from) & (df['dttm'] < dttm_to)
    df.loc[cond, 'lack'] += add


def _lack_calc(df, work_type_id, dttm_from, dttm_to):
    cond = (df.work_type_id==work_type_id) & (df['dttm'] >= dttm_from) & (df['dttm'] < dttm_to)
    return df.loc[cond, 'lack'].apply(
        lambda x:  x if (x < 1.0 and x >-1.0) else 1 if x >= 1 else -1
    ).mean()
