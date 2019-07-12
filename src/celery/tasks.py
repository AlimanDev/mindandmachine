from datetime import date, timedelta
import json

from django.db.models import Avg, Q
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta
# from django.db.models import Q

from src.main.timetable.worker_exchange.utils import (
    # get_init_params,
    # has_deficiency,
    # split_cashiers_periods,
    # intervals_to_shifts,
    search_candidates,
    send_noti2candidates,
    cancel_vacancy,
    confirm_vacancy
)
from src.main.demand.utils import create_predbills_request_function
from src.main.timetable.cashier_demand.utils import get_worker_timetable2 as get_shop_stats

from src.conf.djconfig import (
    QOS_DATETIME_FORMAT,
)
from src.util.models_converter import BaseConverter

from src.main.timetable.worker_exchange.utils import search_candidates, send_noti2candidates
from src.db.models import (
    Event,
    PeriodQueues,
    WorkType,
    CameraCashboxStat,
    WorkerDayCashboxDetails,
    WorkerMonthStat,
    ProductionMonth,
    WorkerDay,
    # Notifications,
    Shop,
    # User,
    ProductionDay,
    WorkerCashboxInfo,
    CameraClientGate,
    CameraClientEvent,
    Timetable,
    IncomeVisitors,
    EmptyOutcomeVisitors,
    PurchasesOutcomeVisitors,
    ExchangeSettings,
)
from src.celery.celery import app
import pandas


@app.task
def update_queue(till_dttm=None):
    """
    Обновляет данные по очереди на всех типах касс

    Args:
        till_dttm(datetime.datetime): до какого времени обновлять?

    Note:
        Выполняется каждые полчаса
    """
    time_step = timedelta(seconds=1800)  # todo: change to supershop step
    if till_dttm is None:
        till_dttm = now() + timedelta(hours=3)  # moscow time

    work_types = WorkType.objects.qos_filter_active(till_dttm + timedelta(minutes=30), till_dttm).filter(
        dttm_last_update_queue__isnull=False,
    )
    if not len(work_types):
        raise ValueError('WorkType EmptyQuerySet with dttm_last_update_queue')
    for work_type in work_types:
        dif_time = till_dttm - work_type.dttm_last_update_queue
        while dif_time > time_step:
            mean_queue = list(CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox__type__id=work_type.id,
                dttm__gte=work_type.dttm_last_update_queue,
                dttm__lt=work_type.dttm_last_update_queue + time_step
            ).values('camera_cashbox_id').annotate(mean_queue=Avg('queue')).values_list('mean_queue', flat=True)) #.filter(mean_queue__gte=0.5)
            # todo: mean_queue__gte seems stupid -- need to change and look only open

            if len(mean_queue):

                min_possible_period_len = max(mean_queue) * 0.17
                mean_queue = list([el for el in mean_queue if el > min_possible_period_len and el > 0.4])
                mean_queue = sum(mean_queue) / (len(mean_queue) + 0.000001)

                changed_amount = PeriodQueues.objects.filter(
                    dttm_forecast=work_type.dttm_last_update_queue,
                    operation_type_id=work_type.work_type_reversed.all()[0].id,
                    type=PeriodQueues.FACT_TYPE,
                ).update(value=mean_queue)
                if changed_amount == 0:
                    PeriodQueues.objects.create(
                        dttm_forecast=work_type.dttm_last_update_queue,
                        type=PeriodQueues.FACT_TYPE,
                        value=mean_queue,
                        operation_type_id=work_type.work_type_reversed.all()[0].id,
                    )

            work_type.dttm_last_update_queue += time_step
            dif_time -= time_step
        work_type.save()


@app.task
def update_visitors_info():
    timestep = timedelta(minutes=30)
    dttm_now = now()
    # todo: исправить потом. пока делаем такую привязку
    # вообще хорошей идеей наверное будет просто cashbox_type blank=True, null=True сделать в PeriodDemand
    try:
        work_type = WorkType.objects.get(name='Кассы', shop_id=1)
    except WorkType.DoesNotExist:
        raise ValueError('Такого типа касс нет в базе данных.')
    create_dict = {
        'work_type': work_type,
        'dttm_forecast': dttm_now.replace(minute=(0 if dttm_now.minute < 30 else 30), second=0, microsecond=0),
        'type': IncomeVisitors.FACT_TYPE
    }

    events_qs = CameraClientEvent.objects.filter(
        dttm__gte=dttm_now - timestep,
        dttm__lte=dttm_now
    )

    income_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_ENTRY,
        type=CameraClientEvent.TYPE_TOWARD,
    ).count()
    empty_outcome_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_ENTRY,
        type=CameraClientEvent.TYPE_BACKWARD,
    ).count()
    purchases_outcome_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_OUT,
        type=CameraClientEvent.TYPE_TOWARD,
    ).count() - events_qs.filter(
        gate__type=CameraClientGate.TYPE_OUT,
        type=CameraClientEvent.TYPE_BACKWARD,
    ).count()

    IncomeVisitors.objects.create(
        value=income_visitors_value,
        **create_dict
    )
    EmptyOutcomeVisitors.objects.create(
        value=empty_outcome_visitors_value,
        **create_dict
    )
    PurchasesOutcomeVisitors.objects.create(
        value=purchases_outcome_visitors_value,
        **create_dict
    )

    print('успешно создал стату по покупателям')


@app.task
def release_all_workers():
    """
    Отпускает всех работников с касс

    Note:
        Выполняется каждую ночь
    """
    worker_day_cashbox_objs = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        dttm_to__isnull=True,
    )

    for obj in worker_day_cashbox_objs:
        obj.on_cashbox = None
        obj.dttm_to = obj.worker_day.dttm_work_end
        obj.save()


@app.task
def update_worker_month_stat():
    """
    Обновляет данные по рабочим дням и часам сотрудников

    Note:
        Обновляется 1 и 15 числа каждого месяца
    """
    dt = now().date().replace(day=1)
    delta = timedelta(days=20)
    dt1 = (dt - delta).replace(day=1)
    dt2 = (dt1 - delta).replace(day=1)
    product_month_1 = ProductionMonth.objects.get(
        dt_first=dt1,
    )
    product_month_2 = ProductionMonth.objects.get(
        dt_first=dt2,
    )
    shops = Shop.objects.all()
    for shop in shops:
        work_hours = 0
        work_days = 0
        # print('начал обновлять worker month stat для {}'.format(shop))

        break_triplets = shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        time_break_triplets = 0
        for triplet in list_of_break_triplets:
            for time_triplet in triplet[2]:
                time_break_triplets += time_triplet
            triplet[2] = time_break_triplets
            time_break_triplets = 0

        worker_days = WorkerDay.objects.qos_current_version().select_related('worker').filter(
            worker__shop=shop,
            dt__lt=dt,
            dt__gte=dt2,
        ).order_by('worker', 'dt')

        last_user = worker_days[0].worker if len(worker_days) else None
        last_month_stat = worker_days[0].dt.month if len(worker_days) else None
        product_month = product_month_1 if last_month_stat == dt1.month else product_month_2

        for worker_day in worker_days:
            time_break_triplets = 0
            duration_of_workerday = 0

            if worker_day.type in WorkerDay.TYPES_PAID:
                if worker_day.type != WorkerDay.Type.TYPE_WORKDAY.value and \
                        worker_day.type != WorkerDay.Type.TYPE_HOLIDAY_WORK.value:
                    duration_of_workerday = ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK]
                else:
                    duration_of_workerday = round((worker_day.dttm_work_end - worker_day.dttm_work_start)
                                                  .total_seconds() / 3600, 3)

                    for triplet in list_of_break_triplets:
                        if float(triplet[0]) < duration_of_workerday * 60 <= float(triplet[1]):
                            time_break_triplets = triplet[2]
                    duration_of_workerday -= round(time_break_triplets / 60, 3)

            if last_user.id == worker_day.worker.id and last_month_stat == worker_day.dt.month:
                if worker_day.type in WorkerDay.TYPES_PAID:
                    work_days += 1
                    work_hours += duration_of_workerday
            else:
                WorkerMonthStat.objects.update_or_create(
                    worker=last_user,
                    month=product_month,
                    defaults={
                        'work_days': work_days,
                        'work_hours': work_hours,
                    })

                work_hours = duration_of_workerday
                work_days = 1 if worker_day.type in WorkerDay.TYPES_PAID else 0
                last_user = worker_day.worker
                last_month_stat = worker_day.dt.month
                product_month = product_month_1 if last_month_stat == dt1.month else product_month_2

        if last_user:
            WorkerMonthStat.objects.update_or_create(
                worker=last_user,
                month=product_month,
                defaults={
                    'work_days': work_days,
                    'work_hours': work_hours,
                })

# @app.task
# def notify_cashiers_lack():
#     """
#     Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров
#
#     Note:
#         Выполняется каждую ночь
#     """
#     for shop in Shop.objects.all():
#         dttm_now = now()
#         notify_days = 7
#         dttm = dttm_now.replace(minute=0, second=0, microsecond=0)
#         init_params_dict = get_init_params(dttm_now, shop.id)
#         work_types = init_params_dict['work_types_dict']
#         mean_bills_per_step = init_params_dict['mean_bills_per_step']
#         period_demands = []
#         for i in range(notify_days):
#             period_demands += get_init_params(dttm_now + datetime.timedelta(days=i), shop.id)['predict_demand']
#
#         managers_dir_list = []
#         users_with_such_notes = []
#         # пока что есть магазы в которых нет касс с ForecastHard
#         if work_types and period_demands:
#             return_dict = has_deficiency(
#                 period_demands,
#                 mean_bills_per_step,
#                 work_types,
#                 dttm,
#                 dttm_now + datetime.timedelta(days=notify_days)
#             )
#             notifications_list = []
#             for dttm_converted in return_dict.keys():
#                 to_notify = False  # есть ли вообще нехватка
#                 hrs, minutes, other = dttm_converted.split(':')  # дропаем секунды
#                 if not shop.super_shop.is_supershop_open_at(datetime.time(hour=int(hrs), minute=int(minutes), second=0)):
#                     continue
#                 if sum(return_dict[dttm_converted].values()) > 0:
#                     to_notify = True
#                     notification_text = '{}:{} {}:\n'.format(hrs, minutes, other[3:])
#                     for work_type in return_dict[dttm_converted].keys():
#                         if return_dict[dttm_converted][work_type]:
#                             notification_text += '{} будет не хватать сотрудников: {}. '.format(
#                                 WorkType.objects.get(id=work_type).name,
#                                 return_dict[dttm_converted][work_type]
#                             )
#                     managers_dir_list = User.objects.filter(
#                         function_group__allowed_functions__func='get_workers_to_exchange',
#                         dt_fired__isnull=True,
#                         shop_id=shop.id
#                     )
#                     users_with_such_notes = []
#
# # TODO: REWRITE WITH EVENT
# # FIXME: REWRITE WITH EVENT
#                     # notes = Notifications.objects.filter(
#                     #     type=Notifications.TYPE_INFO,
#                     #     text=notification_text,
#                     #     dttm_added__lt=now() + datetime.timedelta(hours=2)
#                     # )
#                     # for note in notes:
#                     #     users_with_such_notes.append(note.to_worker_id)
#
#             #     if to_notify:
#             #         for recipient in managers_dir_list:
#             #             if recipient.id not in users_with_such_notes:
#             #                 notifications_list.append(
#             #                     Notifications(
#             #                         type=Notifications.TYPE_INFO,
#             #                         to_worker=recipient,
#             #                         text=notification_text,
#             #                     )
#             #                 )
#             #
#             # Notifications.objects.bulk_create(notifications_list)




@app.task
def create_vacancy_and_notify_cashiers_lack():
    """
    Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров

    """

    exchange_settings = ExchangeSettings.objects.first()
    if not exchange_settings.automatic_check_lack:
        return
    dttm_now = now().replace(minute=0, second=0, microsecond=0)
    dttm_next_week = dttm_now + exchange_settings.automatic_check_lack_timegap
    params = {
        'from_dt': dttm_now.date(),
        'to_dt': dttm_next_week.date(),
    }

    for shop in Shop.objects.all():
        for work_type in shop.worktype_set.all():
            print(work_type)
            params['work_type_ids'] = [work_type.id]
            shop_stat = get_shop_stats(
                shop.id,
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
                continue
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

                for shift in working_shifts:
                    dttm_from = dttm_to
                    dttm_to = dttm_to + shift
                    print('create vacancy {} {} {}'.format(dttm_from, dttm_to, work_type))

                    worker_day_detail = WorkerDayCashboxDetails.objects.create(
                        dttm_from=dttm_from,
                        dttm_to=dttm_to,
                        work_type=work_type,
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



@app.task
def cancel_vacancies():
    """
    Автоматически отменяем вакансии, в которых нет потребности
    :return:
    """
    exchange_settings = ExchangeSettings.objects.first()
    if not exchange_settings.automatic_check_lack:
        return

    from_dt = now().replace(minute=0, second=0, microsecond=0).date()
    to_dt = from_dt + exchange_settings.automatic_check_lack_timegap
    params = {
        'from_dt': from_dt,
        'to_dt': to_dt,
    }

    for shop in Shop.objects.all():
        for work_type in shop.worktype_set.all():
            params['work_type_ids'] = [work_type.id]
            shop_stat = get_shop_stats(
                shop.id,
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
                Q(worker_day__worker__dt_fired__gt=to_dt) | Q(worker_day__worker__dt_fired__isnull=True),
                Q(worker_day__worker__dt_hired__lt=from_dt) | Q(worker_day__worker__dt_hired__isnull=True),
                dttm_from__gte=from_dt,
                dttm_to__lte=to_dt,
                work_type_id__in=[work_type.id],
                is_vacancy=True,
                status__in=work_types,
            ).order_by('status','dttm_from','dttm_to')

            for vacancy in  vacancies:
                cond = (df_stat['dttm'] >= vacancy.dttm_from) & (df_stat['dttm'] <= vacancy.dttm_to)
                overflow = df_stat.loc[cond,'overflow'].apply(lambda x:  x if (x < 1.0 and x >-1.0) else 1 if x >=1 else -1 ).mean()
                if overflow > exchange_settings.automatic_delete_vacancy_oveflow_max:
                    print ('cancel_vacancy overflow {} {} {}'.format(overflow, vacancy, vacancy.dttm_from))
                    cancel_vacancy(vacancy.id)
                    df_stat.loc[cond,'overflow'] -= 1



@app.task
def workers_hard_exchange():
    """

    Автоматически перекидываем сотрудников из других магазинов, если это приносит ценность (todo: добавить описание, что такое ценность).

    :return:
    """
    def lack_calc(df, work_type_id, dttm_from, dttm_to):
        cond = (df.work_type_id==work_type_id) & (df['dttm'] >= dttm_from) & (df['dttm'] <= dttm_to)
        return df.loc[cond, 'lack'].apply(
            lambda x:  x if (x < 1.0 and x >-1.0) else 1 if x >=1 else -1
        ).sum() / 2

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
                vacancy_lack = lack_calc( df_shop_stat, work_type.id, vacancy.dttm_from, vacancy.dttm_to)
                print ('lack vacancy {};;; {}'.format(vacancy_lack, vacancy))
                dttm_from_workers = vacancy.dttm_from - timedelta(hours=4)
                if vacancy_lack > 0:
                    workers = WorkerDayCashboxDetails.objects.filter(
                        dttm_from=vacancy.dttm_from,
                        dttm_to=vacancy.dttm_to,
                        # work_type_id__in=[1],
                        is_vacancy=False,
                        status__in=WorkerDayCashboxDetails.WORK_TYPES_LIST,
                    ).exclude(
                        work_type_id=work_type.id,
                    ).order_by('status','dttm_from','dttm_to')
                    if not len(workers):
                        continue
                    worker_lack = None
                    candidate_to_change = None
                    for worker in workers:
                        lack = lack_calc(df_shop_stat, worker.work_type_id, worker.dttm_from, worker.dttm_to )
                        if worker_lack is None or lack < worker_lack:
                            worker_lack = lack
                            candidate_to_change = worker
                    print ('worker lack  {}'.format(worker_lack))

                    if vacancy_lack - worker_lack > exchange_settings.automatic_worker_select_lack_diff:
                        user = candidate_to_change.worker_day.worker
                        print('hard exchange  worker lack{} vacancy lack {}  candidate_to_change {} to vac {} user {}'.format(worker_lack, vacancy_lack, candidate_to_change, vacancy, user ))
                        candidate_to_change.delete()
                        event = Event.objects.get(workerday_details=vacancy.id)
                        event.do_action(user)



# TODO: REWRITE WITH EVENT
# FIXME: REWRITE WITH EVENT
                    # notes = Notifications.objects.filter(
                    #     type=Notifications.TYPE_INFO,
                    #     text=notification_text,
                    #     dttm_added__lt=now() + datetime.timedelta(hours=2)
                    # )
                    # for note in notes:
                    #     users_with_such_notes.append(note.to_worker_id)

            #     if to_notify:
            #         for recipient in managers_dir_list:
            #             if recipient.id not in users_with_such_notes:
            #                 notifications_list.append(
            #                     Notifications(
            #                         type=Notifications.TYPE_INFO,
            #                         to_worker=recipient,
            #                         text=notification_text,
            #                     )
            #                 )
            #
            # Notifications.objects.bulk_create(notifications_list)


@app.task
def allocation_of_time_for_work_on_cashbox():
    """
    Update the number of worked hours last month for each user in WorkerCashboxInfo
    """

    def update_duration(last_user, last_work_type, duration):
        WorkerCashboxInfo.objects.filter(
            worker=last_user,
            work_type=last_work_type,
        ).update(duration=round(duration, 3))

    dt = now().date().replace(day=1)
    prev_month = dt - relativedelta(months=1)

    for shop in Shop.objects.all():
        work_types = WorkType.objects.qos_filter_active(
            dt_from=prev_month,
            dt_to=dt,
            shop=shop
        )
        last_user = None
        last_work_type = None
        duration = 0

        if len(work_types):
            for work_type in work_types:
                worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related(
                    'worker_day__worker',
                    'worker_day'
                ).filter(
                    status=WorkerDayCashboxDetails.TYPE_WORK,
                    work_type=work_type,
                    on_cashbox__isnull=False,
                    worker_day__dt__gte=prev_month,
                    worker_day__dt__lt=dt,
                    dttm_to__isnull=False,
                    worker_day__worker__dt_fired__isnull=True
                ).order_by('worker_day__worker', 'worker_day__dt')

                for detail in worker_day_cashbox_details:
                    if last_user is None:
                        last_work_type = work_type
                        last_user = detail.worker_day.worker

                    if last_user != detail.worker_day.worker:
                        update_duration(last_user, last_work_type, duration)
                        last_user = detail.worker_day.worker
                        last_work_type = work_type
                        duration = 0

                    duration += (detail.dttm_to - detail.dttm_from).total_seconds() / 3600

            if last_user:
                update_duration(last_user, last_work_type, duration)


@app.task
def create_pred_bills():
    """
    Обновляет данные по спросу

    Note:
        Выполняется первого числа каждого месяца
    """
    # todo: переписать
    for shop in Shop.objects.all():
        create_predbills_request_function(shop.id)
    print('создал спрос на месяц')


@app.task
def clean_camera_stats():
    """
    Удаляет данные с камер за последние for_past_months месяцев

    Note:
        Запускается раз в неделю
    """
    for_past_months = 3
    dttm_to_delete = now() - relativedelta(months=for_past_months)

    CameraCashboxStat.objects.filter(dttm__lt=dttm_to_delete).delete()


@app.task
def update_shop_stats(dt=None):
    if not dt:
        dt = date.today().replace(day=1)
    shops = Shop.objects.filter(dttm_deleted__isnull=True)
    tts = Timetable.objects.filter(shop__in=shops, dt__gte=dt, status=Timetable.Status.READY.value)
    for timetable in tts:
        stats = get_shop_stats(
            shop_id=timetable.shop_id,
            form=dict(
                from_dt=timetable.dt,
                to_dt=timetable.dt + relativedelta(months=1, days=-1),
                work_type_ids=[]
            ),
            indicators_only=True
        )['indicators']
        timetable.idle = stats['deadtime_part']
        timetable.fot = stats['FOT']
        timetable.workers_amount = stats['cashier_amount']
        timetable.revenue = stats['revenue']
        timetable.lack = stats['covering_part']
        timetable.fot_revenue = stats['fot_revenue']
        timetable.save()
