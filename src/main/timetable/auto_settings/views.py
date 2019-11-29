import json
import requests
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.db.models import Q, Sum
from django.utils import timezone

from src.celery.tasks import cancel_shop_vacancies, create_shop_vacancies_and_notify

from src.db.models import (
    Employment,
    Timetable,
    User,
    WorkType,
    PeriodClients,
    WorkerConstraint,
    WorkerCashboxInfo,
    WorkerDay,
    WorkerDayCashboxDetails,
    Shop,
    Slot,
    UserWeekdaySlot,
    ProductionDay,
)
from src.util.collection import group_by
from src.util.models_converter import (
    TimetableConverter,
    WorkTypeConverter,
    EmploymentConverter,
    WorkerConstraintConverter,
    WorkerCashboxInfoConverter,
    WorkerDayConverter,
    BaseConverter,
    UserWeekdaySlotConverter,
)
from src.util.utils import api_method, JsonResponse
from .forms import (
    GetStatusForm,
    SetSelectedCashiersForm,
    CreateTimetableForm,
    DeleteTimetableForm,
    SetTimetableForm,
)

from ..table.utils import count_difference_of_normal_days
from src.main.other.notification.utils import send_notification
from django.db.models import F
from .utils import set_timetable_date_from


@api_method('GET', GetStatusForm)
def get_status(request, form):
    """
    Возвращает статус расписания на данный месяц

    Args:
        method: GET
        url: /api/timetable/auto_settings/get_status
        shop_id(int): required = False
        dt(QOS_DATE): required = True

    Returns:
        {
            'id': id расписания,
            'shop': int,
            'dt': дата расписания,
            'status': статус расписания,
            'dttm_status_change': дата изменения
        }
    """

    try:
        tt = Timetable.objects.get(shop_id=request.shop.id, dt=form['dt'])
    except Timetable.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    return JsonResponse.success(TimetableConverter.convert(tt))


@api_method(
    'POST',
    SetSelectedCashiersForm,
)
def set_selected_cashiers(request, form):
    """
    Проставляет поле auto_timetable = value у заданных сотрудников

    Args:
        method: POST
        url: /api/timetable/auto_settings/set_selected_cashiers
        worker_ids(list): id'шники сотрудников которым проставлять
        shop_id(int): required = True

    Note:
        Всем другим сотрудникам из этого магаза проставляется значение противоположное value
    """
    employments = Employment.objects.filter(shop_id=form['shop_id'])

    if (not form['worker_ids']):
        employments.update(auto_timetable=False)

    employments.filter(
        user_id__in=form['worker_ids']
    ).update(auto_timetable=True)

    employments.exclude(
        user_id__in=form['worker_ids']
    ).update(auto_timetable=False)

    return JsonResponse.success()


@api_method(
    'POST',
    CreateTimetableForm,
)
def create_timetable(request, form):
    """
    Создает request на qos_algo с заданным параметрами

    Args:
        method: POST
        url: /api/timetable/auto_settings/create_timetable
        shop_id(int): required = True
        dt(QOS_DATE): required = True

    Raises:
        JsonResponse.internal_error: если ошибка при составлении расписания

    Note:
        Отправляет уведомление о том, что расписание начало составляться
    """
    """
        Формат данных -- v1.3
        (last updated 16.05.2019):

        demand_list = [
            {
                'dttm_forecast': '23:00:00 07.07.2018',
                'clients': 145,
                'work_type': 1,
            },
            {
                'dttm_forecast': '23:30:00 07.07.2018',
                'clients': 45,
                'work_type': 1,
            },
            ...
        ]

        cashiers = [
            {
                'general_info':
                {
                    'id': 0,
                    'first_name': 'Иван',
                    'last_name': 'Иванов',
                    'middle_name': 'Иванович',
                    'tabel_code': 8090345,
                    'is_fixed_hours': False, # Фиксированный ли график. Если да, то проставляем ему из availabilities смены циклически.
                    На стороне бека все проверки, что корректные данные (по 1 смене на каждый день и нет противоречащих constraints)
                }

                'workdays': [
                    {
                        'dt': '09.09.2018',
                        'type': 'W',
                        'dttm_start': '09:00:00',  #небольшой косяк на беке, но возможно так лучше (хоть и dttm, but field time)
                        'dttm_end': '14:00:00',
                        ''
                    },
                    {
                        'dt': '09.09.2018',
                        'type': 'H',
                        'dttm_start': None,
                        'dttm_end': None,
                    },
                ],

                'prev_data': [
                    {
                        'dt': '28.08.2018',
                        'type': 'W',
                        'dttm_start': '09:00',
                        'dttm_end': '14:00',
                    },
                ],

                'constraints_info': [
                    {
                        'weekday': 0 , # day 0 from [0, week_length - 1]
                        'week_length': 7,  # длина интервала, для которого заданы constraints (строго от 2 до 7). Этот интервал циклически растягивается на месяц ( с учетом стыковки с прошлым)
                        'tm': '09:00',
                        'is_lite': True,  # жесткие ли ограничения
                    }
                ],

                # кроме ограничений, бывает еще и наоборот указаны доступности в сменах. Constraints идут в приоритете,
                # так что сначала парсятся доступности, а потом ограничения поверх них.
                'availability_info': [
                    {
                        'weekday': 0 , # day 0 from [0, week_length - 1]
                        'week_length': 4,  # длина интервала, для которого заданы available смены (строго от 2 до 7). Этот интервал циклически растягивается на месяц ( с учетом стыковки с прошлым)
                         # здесь должно быть прописано явно, на каких сменах может работать, каждое ограничение -- инфа про конкретную смену
                        'is_suitable': True,  # желательная ли смена (если True, то зеленая, если False, то желтая)
                        'slot':
                            {
                                'tm_start': '10:00:00',
                                'tm_end': '19:00:00,
                            },
                    },
                ],

                'worker_cashbox_info': [
                    {
                        'work_type': 1,
                        'mean_speed': 1.4,
                    }
                ],

                'norm_work_amount': 160,  # сколько по норме часов надо отработать за этот месяц
                'required_coupled_hol_in_hol': 0,  # сколько должно быть спаренных выходных в выходные у чувака
                'min_shift_len': 4,  # минимальная длина смены
                'max_shift_len': 12,  # максимальная длина смены
                'min_time_between_slots': 12,  # минимальное время между сменами
            }
        ]

        work_types = [
            {
                'id': 1,
                'name': 'Касса',
                'prior_weight': 2.5,
                'slots': [
                    {
                        'tm_start': '10:00:00',
                        'tm_end': '19:00:00,
                    },
                    {
                        'tm_start': '22:00:00',
                        'tm_end': '07:00:00',
                    },
                ],
                'min_workers_amount': 1,
                'max_workers_amount': 6,
            },
            {
                'id': 2,
                'prior_weight': 1,
                'slots': [],
            },
        ]

        shop_info = {
            'period_step': 30, int, делитель 60 (15, 30, 60),
            'tm_start_work': '07:00:00',
            'tm_end_work': '01:00:00',

            'min_work_period': 60 * 6,
            'max_work_period': 60 * 12,

            'max_work_coef': 1.15,
            'min_work_coef': 0.85,

            'tm_lock_start': ['12:30', '13:00', '00:00', '00:30', '01:00'],
            'tm_lock_end': [],

            'hours_between_slots': 12,

            'max_work_hours_7days': 46, # сколько максимум часов можно отработать любому чуваку за любые 7 дней подряд

            'morning_evening_same': False,  # флаг, учитывать ли равномерность по утренним и вечерним сменам при составлении
            'workdays_holidays_same': False # флаг, учитывать ли равномерность по работе чуваков в будни и выхи при составлении
            'fot': 0, # если не 0, то считается ограничением суммарного фота (в часах) на магазин.
            Алго будет пытаться равномерно распределить это между чуваками. Ну, не совсем втупую, с учетом отпусков.
            При этом индивидуальные часы игнорируются.
            'idle': 0, # ограничение на простой
            'slider': 3.2, # ползунок, который каким-то образом влияет на составление и отражает что-то вроде допустимой
            средней длины очереди. Пока интерпретируется как "чем меньше, чем больше сотрудников нужно вывести". Бегает
            от 1 до 10, float.

            # пока не используемые
            'mean_queue_length': 2.3,
            'max_queue_length': 4,
            'dead_time_part': 0.1,
            'max_outsourcing_day': 3,
            '1day_holiday': 0,

        }

        break_triplets = [[240, 420, [15, 30, 15]],
                          [420, 720, [15, 30, 15, 30, 15]],
                         ]

    """

    shop_id = form['shop_id']

    dt_from = set_timetable_date_from(form['dt'].year, form['dt'].month)
    if not dt_from:
        return JsonResponse.value_error('Нельзя изменить расписание за прошедший месяц')

    dt_first = dt_from.replace(day=1)
    dt_to = (dt_first + relativedelta(months=1))

    try:
        tt = Timetable.objects.create(
            shop_id=shop_id,
            dt=dt_first,
            status=Timetable.PROCESSING,
            dttm_status_change=datetime.now()
        )
    except:
        return JsonResponse.already_exists_error()

    employments=Employment.objects.get_active(
        dt_from,
        dt_to,
        shop_id=shop_id,
        auto_timetable=True,
    ).select_related('user')

    employment_ids = employments.values_list('user_id', flat=True)

    users = User.objects.filter(id__in=employment_ids)
    user_dict = {u.id: u for u in users}

    shop = request.shop

    period_step = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute

    ########### Проверки ###########

    # проверка что у всех юзеров указаны специализации
    users_without_spec = []
    for employment in employments:
        worker_cashbox_info = WorkerCashboxInfo.objects.filter(
            worker=employment,
            is_active='True'
        )
        if not worker_cashbox_info.exists():
            users_without_spec.append(employment.user.first_name + ' ' + employment.user.last_name)
    if users_without_spec:
        tt.status = Timetable.ERROR
        status_message = 'Не проставлены типы работ у пользователей: {}.'.format(', '.join(users_without_spec))
        tt.delete()
        return JsonResponse.value_error(status_message)

    # проверка что есть спрос на период
    period_difference = {'work_type_name': [], 'difference': []}

    hours_opened = round((datetime.combine(date.today(), shop.tm_shop_closes) -
                                  datetime.combine(date.today(), shop.tm_shop_opens)).seconds / 3600)
    if hours_opened == 0:
        hours_opened = 24
    period_normal_count = int(hours_opened * ((dt_to - dt_from).days) * (60 / period_step))

    work_types = WorkType.objects.qos_filter_active(
        dt_from=dt_from,
        dt_to=dt_to,
        shop_id=shop_id
    )
    for work_type in work_types:
        periods_len = PeriodClients.objects.filter(
            operation_type__dttm_deleted__isnull=True,
            operation_type__work_type=work_type,
            type=PeriodClients.LONG_FORECASE_TYPE,
            dttm_forecast__date__gte=dt_from,
            dttm_forecast__date__lt=dt_to,
        ).count()

        if periods_len % period_normal_count:
            period_difference['work_type_name'].append(work_type.name)
            period_difference['difference'].append(abs(period_normal_count - periods_len))
    if period_difference['work_type_name']:
        status_message = 'На типе работ {} не хватает объектов спроса {}.'.format(
            ', '.join(period_difference['work_type_name']),
            ', '.join(str(x) for x in period_difference['difference'])
        )
        tt.delete()
        return JsonResponse.value_error(status_message)
    
    # проверки для фиксированных чуваков
    # Возможности сотрудников
    availabilities = group_by(
        collection=UserWeekdaySlot.objects.select_related('worker').filter(
            employment__shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )
    for employment in employments:
        user_id = employment.user_id
        user = user_dict[user_id]
        if employment.is_fixed_hours:
            availability_info = availabilities.get(user_id, [])
            if not (len(availability_info)):
                print(f'Warning! User {user_id} {user.last_name} {user.first_name} с фиксированными часами, но нет набора смен, на которых может работать!')
            mask = [0 for _ in range(len(availability_info))]
            for info_day in availability_info:
                mask[info_day.weekday] += 1
            if mask.count(1) != len(mask):
                status_message = f'Ошибка! Работник {user_id} {user.last_name} {user.first_name} с фиксированными часами, но на один день выбрано больше одной смены)!'
                tt.delete()
                return JsonResponse.value_error(status_message)
    
    ##################################################################

    # Функция для заполнения расписания
    def fill_wd_array(worker_days_db, array):
        worker_days_mask = {}
        for wd in worker_days_db:
            if (wd['id'] in worker_days_mask) and wd['work_types__id']:
                continue

            worker_days_mask[wd['id']] = len(array)
            wd_mod = WorkerDay(
                id=wd['id'],
                type=wd['type'],
                dttm_added=wd['dttm_added'],
                dt=wd['dt'],
                worker_id=wd['worker_id'],
                dttm_work_start=wd['dttm_work_start'],
                dttm_work_end=wd['dttm_work_end'],
            )
            wd_mod.work_type_id = wd['work_types__id'] if wd['work_types__id'] else None
            array.append(wd_mod)


    new_worker_days = []
    worker_days_db = WorkerDay.objects.qos_current_version().select_related('worker').filter(
        shop_id=form['shop_id'],
        dt__gte=dt_from,
        dt__lt=dt_to,
    ).exclude(
        type=WorkerDay.TYPE_EMPTY
    ).order_by(
        'dt'
    ).values(
        'id',
        'type',
        'dttm_added',
        'dt',
        'worker_id',
        'dttm_work_start',
        'dttm_work_end',
        'work_types__id',
    )
    fill_wd_array(worker_days_db, new_worker_days)

    prev_worker_days = []
    worker_days_db = WorkerDay.objects.qos_current_version().select_related('worker').filter(
        employment__shop_id=form['shop_id'],
        dt__gte=dt_from - timedelta(days=7),
        dt__lte=dt_from,
    ).exclude(
        type=WorkerDay.TYPE_EMPTY
    ).order_by(
        'dt'
    ).values(
        'id',
        'type',
        'dttm_added',
        'dt',
        'worker_id',
        'dttm_work_start',
        'dttm_work_end',
        'work_types__id',
    )
    fill_wd_array(worker_days_db, prev_worker_days)


    if shop.process_type == Shop.YEAR_NORM:
        max_work_coef = (1 + shop.more_norm / 100)
        min_work_coef = (1 - shop.less_norm / 100)
    else:
        max_work_coef = 1
        min_work_coef = 1

    shop_dict = {
        'shop_name': shop.title,
        'process_type': shop.process_type,
        'mean_queue_length': shop.mean_queue_length,
        'max_queue_length': shop.max_queue_length,
        'dead_time_part': shop.dead_time_part,
        'max_work_coef': max_work_coef,
        'min_work_coef': min_work_coef,
        'period_step': period_step,
        'tm_start_work': BaseConverter.convert_time(shop.tm_shop_opens),
        'tm_end_work': BaseConverter.convert_time(shop.tm_shop_closes),
        'min_work_period': shop.shift_start * 60,
        'max_work_period': shop.shift_end * 60,
        'tm_lock_start': list(map(lambda x: x + ':00', json.loads(shop.restricted_start_times))),
        'tm_lock_end': list(map(lambda x: x + ':00', json.loads(shop.restricted_end_times))),
        'hours_between_slots': shop.min_change_time,
        'morning_evening_same': shop.even_shift_morning_evening,
        'workdays_holidays_same': False, #TODO(as): флаг, учитывать ли равномерность по работе чуваков в будни и выхи при составлении (нет на фронте)
        '1day_holiday': int(shop.exit1day),
        'max_outsourcing_day': 3,
        'max_work_hours_7days': int(shop.max_work_hours_7days),
        'slider': shop.queue_length,
        'fot': shop.fot,
        'idle': shop.idle,
    }


    ########### Группируем ###########

    # Ограничения сотрудников
    constraints = group_by(
        collection=WorkerConstraint.objects.select_related('worker').filter(
            employment__shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )
    work_types = {
        x.id: dict(WorkTypeConverter.convert(x),slots=[])  for x in WorkType.objects.filter(
            dttm_deleted__isnull=True,
            shop_id=shop_id,
        )
    }

    slots=Slot.objects.filter(shop_id=shop_id, work_type_id__isnull=False)
    for slot in slots:
        work_types[slot.work_type_id]['slots'].append({
            'tm_start': BaseConverter.convert_time(slot.tm_start),
            'tm_end': BaseConverter.convert_time(slot.tm_end),
        })

    # Информация по кассам для каждого сотрудника
    need_work_types = WorkType.objects.filter(shop_id=shop_id).values_list('id', flat=True)
    worker_cashbox_info = group_by(
        collection=WorkerCashboxInfo.objects.filter(work_type_id__in=need_work_types, is_active=True),
        group_key=lambda x: x.worker.user_id
    )

    # Уже составленное расписание
    worker_day = group_by(
        collection=new_worker_days,
        group_key=lambda x: x.worker_id
    )

    # Расписание за прошлую неделю от даты составления
    prev_data = group_by(
        collection=prev_worker_days,
        group_key=lambda x: x.worker_id
    )
    employment_stat_dict = count_difference_of_normal_days(dt_end=dt_from, employments=employments)


   

    ##################################################################

    # если стоит флаг shop.paired_weekday, смотрим по юзерам, нужны ли им в этом месяце выходные в выходные
    resting_states_list = [WorkerDay.TYPE_HOLIDAY]
    if shop.paired_weekday:
        for employment in employments:
            coupled_weekdays = 0
            month_info = prev_data.get(employment.user_id, [])
            for day in range(len(month_info) - 1):
                day_info = month_info[day]
                if day_info.dt.weekday() == 5 and day_info.type in resting_states_list:
                    next_day_info = month_info[day + 1]
                    if next_day_info.dt.weekday() == 6 and next_day_info.type in resting_states_list:
                        coupled_weekdays += 1

            employment_stat_dict[employment.id]['required_coupled_hol_in_hol'] = 0 if coupled_weekdays else 1

    ########### Корректировка рабочих ###########
    dates = [dt_from + timedelta(days=i) for i in range((dt_to -  dt_from).days)]
    for employment in employments:
        # Для уволенных сотрудников
        if employment.dt_fired:
            employment.is_fixed_hours = True
            workers_month_days = worker_day.get(employment.user_id, []) # Может случиться так что для этого работника еще никаким образом расписание не составлялось
            workers_month_days.sort(key=lambda wd: wd.dt)
            workers_month_days_new = []
            wd_index = 0
            for dt in dates:
                if (workers_month_days[wd_index].dt if\
                     wd_index < len(workers_month_days) else None) and dt < employment.dt_fired: #Если вернется пустой список, нужно исключать ошибку out of range
                    workers_month_days_new.append(workers_month_days[wd_index])
                    wd_index += 1
                elif dt < employment.dt_fired and employment.auto_timetable:
                    continue
                else:
                    workers_month_days_new.append(WorkerDay(
                            type=WorkerDay.TYPE_HOLIDAY,
                            dt=dt,
                            worker_id=employment.user_id,
                        )
                    )
            worker_day[employment.user_id] = workers_month_days_new 
        # Если для сотрудника не составляем расписание, его все равно нужно учитывать, так как он покрывает спрос
        # Реализация через фиксированных сотрудников, чтобы не повторять функционал
        elif not employment.auto_timetable:
            employment.is_fixed_hours = True
            workers_month_days = worker_day.get(employment.user_id, []) # Может случиться так что для этого работника еще никаким образом расписание не составлялось
            workers_month_days.sort(key=lambda wd: wd.dt)
            workers_month_days_new = []
            wd_index = 0
            for dt in dates:
                if (workers_month_days[wd_index].dt if\
                     wd_index < len(workers_month_days) else None) == dt: #Если вернется пустой список, нужно исключать ошибку out of range
                    workers_month_days_new.append(workers_month_days[wd_index])
                    wd_index += 1
                else:
                    workers_month_days_new.append(WorkerDay(
                        type=WorkerDay.TYPE_HOLIDAY,
                        dt=dt,
                        worker_id=employment.user_id,
                    ))
            worker_day[employment.user_id] = workers_month_days_new
    
    ##################################################################

    ########### Выборки из базы данных ###########

    # Спрос
    periods = PeriodClients.objects.filter(
        operation_type__dttm_deleted__isnull=True,
        operation_type__work_type__shop_id=shop_id,
        operation_type__work_type__dttm_deleted__isnull=True,
        type=PeriodClients.LONG_FORECASE_TYPE,
        dttm_forecast__date__gte=dt_from,
        dttm_forecast__date__lt=dt_to,
    ).values(
        'dttm_forecast',
        'operation_type__work_type_id',
    ).annotate(
        clients=Sum(F('value') / (period_step / F('operation_type__speed_coef')) * (1.0 + (shop.absenteeism / 100)))
    ).values_list(
        'dttm_forecast',
        'operation_type__work_type_id',
        'clients'
    )

    demands = [{
        'dttm_forecast': BaseConverter.convert_datetime(x[0]),
        'work_type': x[1],
        'clients': x[2],
    } for x in periods]


    # Параметры инициализации
    init_params = json.loads(shop.init_params)
    work_days = list(ProductionDay.objects.filter(
        dt__gte=dt_from,
        dt__lt=dt_to,
        type__in=ProductionDay.WORK_TYPES,
    ))
    work_hours = sum([ProductionDay.WORK_NORM_HOURS[wd.type] for wd in work_days])  # норма рабочего времени за период (за месяц)

    init_params['n_working_days_optimal'] = len(work_days)

    ##################################################################

    data = {
        'IP': settings.HOST_IP,
        'timetable_id': tt.id,
        'forecast_step_minutes': shop.forecast_step_minutes.minute,
        'work_types': list(work_types.values()),
        'shop': shop_dict,
        'demand': demands,
        'cashiers': [
            {
                'general_info': EmploymentConverter.convert(e),
                'constraints_info': [WorkerConstraintConverter.convert(x) for x in constraints.get(e.user_id, [])],
                'availability_info': [UserWeekdaySlotConverter.convert(x) for x in availabilities.get(e.user_id, [])],
                'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(e.user_id, [])],
                'workdays': [WorkerDayConverter.convert(x) for x in worker_day.get(e.user_id, [])],
                'prev_data': [WorkerDayConverter.convert(x) for x in prev_data.get(e.user_id, [])],
                'overworking_hours': employment_stat_dict[e.id].get('diff_prev_paid_hours', 0),
                'overworking_days': employment_stat_dict[e.id].get('diff_prev_paid_days', 0),
                'norm_work_amount': work_hours * e.norm_work_hours / 100,
                'required_coupled_hol_in_hol': employment_stat_dict[e.id].get('required_coupled_hol_in_hol', 0),
                'min_shift_len': e.shift_hours_length_min if e.shift_hours_length_min else 0,
                'max_shift_len': e.shift_hours_length_max if e.shift_hours_length_max else 24,
                'min_time_between_slots': e.min_time_btw_shifts if e.min_time_btw_shifts else 0,
                'dt_new_week_availability_from': BaseConverter.convert_date(e.dt_new_week_availability_from),
            }
            for e in employments
        ],
        'algo_params': {
            'min_add_coef': shop.mean_queue_length,
            'cost_weights': json.loads(shop.cost_weights),
            'method_params': json.loads(shop.method_params),
            'breaks_triplets': json.loads(shop.break_triplets),
            'init_params': init_params,
        },
    }

    tt.save()
    data = json.dumps(data).encode('ascii')
    try:
        r= requests.post('http://{}/'.format(settings.TIMETABLE_IP), data=data )
        res = r.json()

        tt.task_id = res.get('task_id', '')
        if tt.task_id is None:
            tt.status = Timetable.ERROR
            tt.save()
    except Exception as e:

        print(e.with_traceback())
        tt.status = Timetable.ERROR

        tt.status_message = str(e)
        tt.save()
        return JsonResponse.internal_error('Error sending data to server')

    send_notification('C', tt, sender=request.user)
    return JsonResponse.success()


@api_method(
    'POST',
    DeleteTimetableForm,
)
def delete_timetable(request, form):
    """
    Удаляет расписание на заданный месяц. Также отправляет request на qos_algo на остановку задачи в селери

    Args:
        method: POST
        url: /api/timetable/auto_settings/delete_timetable
        shop_id(int): required = True
        dt(QOS_DATE): required = True

    Note:
        Отправляет уведомление о том, что расписание было удалено
    """
    shop_id = form['shop_id']

    dt_from = set_timetable_date_from(form['dt'].year, form['dt'].month)
    if not dt_from:
        return JsonResponse.value_error('Cannot delete past month')
    dt_first = dt_from.replace(day=1)
    dt_to = (dt_first + relativedelta(months=1))

    tts = Timetable.objects.filter(shop_id=shop_id, dt=dt_first)
    for tt in tts:
        if (tt.status == Timetable.PROCESSING) and (not tt.task_id is None):
            try:
                requests.post(
                    'http://{}/delete_task'.format(settings.TIMETABLE_IP), data=json.dumps({'id': tt.task_id}).encode('ascii')
                )
            except (requests.ConnectionError, requests.ConnectTimeout):
                pass
            send_notification('D', tt, sender=request.user)
    tts.delete()


    WorkerDayCashboxDetails.objects.filter(
        worker_day__employment__shop_id=shop_id,
        worker_day__dt__gte=dt_from,
        worker_day__dt__lt=dt_to,
        worker_day__employment__auto_timetable=True,
        is_vacancy=False,
    ).filter(
        Q(worker_day__created_by__isnull=True) |
        Q(worker_day__type=WorkerDay.TYPE_EMPTY)
    ).update(
        dttm_deleted=timezone.now()
    )

    WorkerDayCashboxDetails.objects.filter(
        worker_day__employment__shop_id=shop_id,
        worker_day__dt__gte=dt_from,
        worker_day__dt__lt=dt_to,
        worker_day__employment__auto_timetable=True,
        is_vacancy=True,
    ).update(
        worker_day=None
    )

    wdays = WorkerDay.objects.filter(
        employment__shop_id=shop_id,
        dt__gte=dt_from,
        dt__lt=dt_to,
        employment__auto_timetable=True,
        child__id__isnull=True
    ).filter(
        created_by__isnull=True,
    ).exclude(
        type=WorkerDay.TYPE_EMPTY
    )
    wds = [WorkerDay(
        type=WorkerDay.TYPE_EMPTY,
        dt = wd.dt,
        parent_worker_day=wd,
        worker_id=wd.worker_id,
    ) for wd in wdays]
    WorkerDay.objects.bulk_create(wds)

    # cancel vacancy
    # todo: add deleting workerdays
    work_type_ids = [w.id for w in WorkType.objects.filter(shop_id=shop_id)]
    WorkerDayCashboxDetails.objects.filter(
        dttm_from__date__gte=dt_from,
        dttm_from__date__lt=dt_to,
        is_vacancy=True,
        work_type_id__in=work_type_ids,
    ).update(
        dttm_deleted=timezone.now(),
        status=WorkerDayCashboxDetails.TYPE_DELETED,
    )

    return JsonResponse.success()


# @csrf_exempt
#@api_method('POST', SetTimetableForm, auth_required=False)
@api_method('POST',
            SetTimetableForm,
            lambda_func=lambda x: Timetable.objects.get(id=x['timetable_id']).shop
)
def set_timetable(request, form):
    """
    Ждет request'a от qos_algo. Когда получает, записывает данные по расписанию в бд

    Args:
        method: POST
        url: /api/timetable/auto_settings/set_timetable
        data(str): json data с данными от qos_algo

    Raises:
        JsonResponse.does_not_exists_error: если расписания нет в бд

    Note:
        Отправляет уведомление о том, что расписание успешно было создано
    """

    try:
        data = json.loads(form['data'])
    except:
        return JsonResponse.internal_error('cannot parse json')

    timetable = Timetable.objects.get(id=form['timetable_id'])

    shop = request.shop

    timetable.status = data['timetable_status']
    timetable.status_message = data.get('status_message', False)
    timetable.save()
    if timetable.status != Timetable.READY and timetable.status_message:
        return JsonResponse.success(timetable.status_message)

    if data['users']:
        users = {x.id: x for x in User.objects.filter(id__in=list(data['users']))}
        employments = {x.user_id: x for x in Employment.objects.get_active(
            dt_from=timetable.dt,
            dt_to=timetable.dt+relativedelta(months=1),
            shop=shop,
            user_id__in=list(data['users']))}

        for uid, v in data['users'].items():
            uid = int(uid)
            for wd in v['workdays']:
                # todo: actually use a form here is better
                # todo: too much request to db

                dt = BaseConverter.parse_date(wd['dt'])
                wd_obj = WorkerDay(
                    dt=dt,
                    worker_id=uid,
                    shop=shop,
                    employment=employments[uid],
                    type=wd['type']
                )

                parent_wd_obj = WorkerDay.objects.filter(
                    worker_id=uid,
                    shop=shop,
                    dt=dt,
                    child__id__isnull=True
                ).first()

                if parent_wd_obj:
                    if parent_wd_obj.type != WorkerDay.TYPE_EMPTY:
                        continue
                    wd_obj.parent_worker_day = parent_wd_obj

                if WorkerDay.is_type_with_tm_range(wd_obj.type):
                    wd_obj.dttm_work_start = BaseConverter.parse_datetime(wd['dttm_work_start'])
                    wd_obj.dttm_work_end = BaseConverter.parse_datetime(wd['dttm_work_end'])
                    wd_obj.save()

                    WorkerDayCashboxDetails.objects.filter(worker_day=wd_obj).delete()
                    wdd_list = []

                    for wdd in wd['details']:
                        wdd_el = WorkerDayCashboxDetails(
                            worker_day=wd_obj,
                            dttm_from=BaseConverter.parse_datetime(wdd['dttm_from']),
                            dttm_to=BaseConverter.parse_datetime(wdd['dttm_to']),
                        )
                        if wdd['type'] > 0:
                            wdd_el.work_type_id = wdd['type']
                        else:
                            wdd_el.status = WorkerDayCashboxDetails.TYPE_BREAK

                        wdd_list.append(wdd_el)
                    WorkerDayCashboxDetails.objects.bulk_create(wdd_list)

                else:
                    wd_obj.save()

        send_notification('C', timetable)

        for work_type in request.shop.worktype_set.all():
            cancel_shop_vacancies.apply_async((request.shop.id, work_type.id))
            create_shop_vacancies_and_notify.apply_async((request.shop.id, work_type.id))

    return JsonResponse.success()
