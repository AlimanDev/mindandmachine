import json
import requests
from datetime import datetime, timedelta, date
from django.conf import settings
from django.db.models import F, Count, Sum, Q
from django.db.models.functions import Coalesce, Extract

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from src.celery.tasks import create_shop_vacancies_and_notify, cancel_shop_vacancies
from src.base.permissions import Permission
from src.base.exceptions import MessageError

from src.forecast.models import PeriodClients
from src.base.models import Shop, Employment, User, ProductionDay, ShopSettings
from src.timetable.models import (
    ShopMonthStat,
    WorkType,
    WorkerConstraint,
    EmploymentWorkType,
    WorkerDay,
    WorkerDayCashboxDetails,
    Slot,
    UserWeekdaySlot,
)

from src.timetable.serializers import AutoSettingsSerializer
from src.util.models_converter import (
    WorkTypeConverter,
    EmploymentConverter,
    WorkerDayConverter,
    Converter,
)

from src.timetable.worker_day.stat import CalendarPaidDays
from rest_framework.exceptions import ValidationError, AuthenticationFailed
from rest_framework.authentication import BaseAuthentication
REBUILD_TIMETABLE_MIN_DELTA = 2

class TokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        token = request.data.get('access_token') or request.query_params.get('access_token')
        if not token:
            return None

        try:
            user = User.objects.get(access_token=token)
        except User.DoesNotExist:
            raise AuthenticationFailed('No such user')

        return (user, None)

class AutoSettingsViewSet(viewsets.ViewSet):
    serializer_class = AutoSettingsSerializer
    permission_classes = [Permission]
    basename = 'AutoSettings'

    @action(detail=False, methods=['post'])
    def create_timetable(self, request):
        """
        :params: shop_id, dt_from, dt_to, is_remarking
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

        :param request:
        :return:
        """

        ####################################################
        #  specially for 585 gold!!!
        def get_position_status(employment):
            pos_status = 0
            if employment.position:
                if employment.position.code == '1':
                    pos_status = 1
                elif employment.position.code == '2':
                    pos_status = 2
                else:
                    pos_status = 0
            return pos_status

        ####################################################

        serializer = AutoSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        form = serializer.validated_data

        shop_id = form['shop_id']
        dt_from = form['dt_from']
        dt_to = form['dt_to']

        dt_min = datetime.now().date() + timedelta(days=REBUILD_TIMETABLE_MIN_DELTA)

        if dt_from < dt_min:
            raise MessageError("tt_create_past")

        dt_first = dt_from.replace(day=1)

        try:
            tt = ShopMonthStat.objects.create(
                shop_id=shop_id,
                dt=dt_first,
                status=ShopMonthStat.PROCESSING,
                dttm_status_change=datetime.now()
            )
        except:
            if (form['is_remaking']):
                tt = ShopMonthStat.objects.get(shop_id=shop_id, dt=dt_first)
                tt.status = ShopMonthStat.PROCESSING
                tt.dttm_status_change = datetime.now()
                tt.save()
            else:
                raise MessageError("tt_exists")

        employments = Employment.objects.get_active(
            dt_from=dt_from,
            dt_to=dt_to,
            shop_id=shop_id,
            # auto_timetable=True, чтобы все сотрудники были, так как пересоставляем иногда для 1
        ).select_related('user', 'position')

        user_ids = employments.values_list('user_id', flat=True)

        users = User.objects.filter(id__in=user_ids)
        user_dict = {u.id: u for u in users}

        shop = Shop.objects.get(id=shop_id)

        period_step = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute

        ########### Проверки ###########

        # проверка что у всех юзеров указаны специализации
        users_without_spec = []
        for employment in employments:
            employment_work_type = EmploymentWorkType.objects.filter(
                employment=employment,
                is_active='True'
            )
            if not employment_work_type.exists():
                users_without_spec.append(employment.user.first_name + ' ' + employment.user.last_name)
        if users_without_spec:
            tt.status = ShopMonthStat.ERROR
            tt.delete()
            raise MessageError("tt_users_without_spec", params={'users': ', '.join(users_without_spec)})

        # проверка что есть спрос на период
        # period_difference = {'work_type_name': [], 'difference': []}

        # hours_opened = round((datetime.combine(date.today(), shop.tm_shop_closes) -
        #                       datetime.combine(date.today(), shop.tm_shop_opens)).seconds / 3600)
        # if hours_opened == 0:
            hours_opened = 24
        # period_normal_count = int(hours_opened * ((dt_to - dt_from).days) * (60 / period_step))

        # work_types = WorkType.objects.qos_filter_active(
        #     dt_from=dt_from,
        #     dt_to=dt_to,
        #     shop_id=shop_id
        # ).select_related(
        #     'work_type_name',
        # )

        # fixme: плохая проверка на наличие всех полей -- могут быть 0 и из-за этого постоянно не проходит проверка
        # лучше сделать проверку по дням
        # for work_type in work_types:
        #     periods_len = PeriodClients.objects.filter(
        #         operation_type__dttm_deleted__isnull=True,
        #         operation_type__work_type=work_type,
        #         type=PeriodClients.LONG_FORECASE_TYPE,
        #         dttm_forecast__date__gte=dt_from,
        #         dttm_forecast__date__lt=dt_to,
        #         dttm_forecast__time__gte=shop.tm_shop_opens,
        #         dttm_forecast__time__lt=shop.tm_shop_closes,
        #
        #
        #
        #     ).count()
        #
        #     if periods_len % period_normal_count:
        #         period_difference['work_type_name'].append(work_type.work_type_name.name)
        #         period_difference['difference'].append(abs(period_normal_count - periods_len))
        # if period_difference['work_type_name']:
        #     status_message = 'На типе работ {} не хватает объектов спроса {}.'.format(
        #         ', '.join(period_difference['work_type_name']),
        #         ', '.join(str(x) for x in period_difference['difference'])
        #     )
        #     tt.delete()
        #     return JsonResponse.value_error(status_message)

        # проверки для фиксированных чуваков
        # Возможности сотрудников
        availabilities = {}
        for user_weekday_slot in list(UserWeekdaySlot.objects.select_related('worker', 'employment').filter(
                employment__shop_id=shop_id)):
            key = user_weekday_slot.worker_id
            if key not in availabilities:
                availabilities[key] = []
            availabilities[key].append(user_weekday_slot)
        for employment in employments:
            user_id = employment.user_id
            user = user_dict[user_id]
            if employment.is_fixed_hours:
                availability_info = availabilities.get(user_id, [])
                if not (len(availability_info)):
                    print(f'Warning! User {user_id} {user.last_name} {user.first_name} с фиксированными часами, '
                          f'но нет набора смен, на которых может работать!')
                mask = [0 for _ in range(len(availability_info))]
                for info_day in availability_info:
                    mask[info_day.weekday] += 1
                if mask.count(1) != len(mask):
                    tt.delete()
                    raise MessageError('tt_user_extra_shifts', {'user': user})

        ##################################################################

        # Функция для заполнения расписания
        def fill_wd_array(worker_days_db, array, prev_data=False):
            worker_days_mask = {}
            for wd in worker_days_db:
                if ((wd['id'] in worker_days_mask) and wd['work_types__id']) or \
                        ((prev_data == False) and (wd['type'] == WorkerDay.TYPE_HOLIDAY) and (
                                wd['created_by_id'] is None)):
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
                    created_by_id=wd['created_by_id'],
                )
                wd_mod.work_type_id = wd['work_types__id'] if wd['work_types__id'] else None
                array.append(wd_mod)

        new_worker_days = []
        worker_days_db = WorkerDay.objects.get_last_plan(
            worker_id__in=user_ids,
            dt__gte=dt_from,
            dt__lt=dt_to,
        ).order_by(
            'dt', 'worker_id'
        ).values(
            'id',
            'type',
            'dttm_added',
            'dt',
            'worker_id',
            'dttm_work_start',
            'dttm_work_end',
            'work_types__id',
            'created_by_id',
        )
        fill_wd_array(worker_days_db, new_worker_days, prev_data=form.get('is_remaking', False))

        prev_worker_days = []
        worker_days_db = WorkerDay.objects.get_last_plan(
            worker_id__in=user_ids,
            dt__gte=dt_from - timedelta(days=7),
            dt__lt=dt_from,
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
            'created_by_id',
        )
        fill_wd_array(worker_days_db, prev_worker_days, prev_data=True)

        max_work_coef = 1
        min_work_coef = 1
        if shop.settings.process_type == ShopSettings.YEAR_NORM:
            max_work_coef += shop.settings.more_norm / 100
            min_work_coef -= shop.settings.less_norm / 100

        shop_dict = {
            'shop_name': shop.name,
            'process_type': shop.settings.process_type,
            'mean_queue_length': shop.mean_queue_length,
            'max_queue_length': shop.max_queue_length,
            'dead_time_part': shop.dead_time_part,
            'max_work_coef': max_work_coef,
            'min_work_coef': min_work_coef,
            'period_step': period_step,
            'tm_start_work': Converter.convert_time(shop.tm_shop_opens),
            'tm_end_work': Converter.convert_time(shop.tm_shop_closes),
            'min_work_period': shop.settings.shift_start * 60,
            'max_work_period': shop.settings.shift_end * 60,
            'tm_lock_start': list(map(lambda x: x + ':00', json.loads(shop.restricted_start_times))),
            'tm_lock_end': list(map(lambda x: x + ':00', json.loads(shop.restricted_end_times))),
            'hours_between_slots': shop.settings.min_change_time,
            'morning_evening_same': shop.settings.even_shift_morning_evening,
            'workdays_holidays_same': False,
            # TODO(as): флаг, учитывать ли равномерность по работе чуваков в будни и выхи при составлении (нет на фронте)
            '1day_holiday': int(shop.settings.exit1day),
            'max_outsourcing_day': 3,
            'max_work_hours_7days': int(shop.settings.max_work_hours_7days),
            'slider': shop.settings.queue_length,
            'fot': 0,  # fixme: tmp, special for 585
            'idle': shop.settings.idle,
            'is_remaking': form['is_remaking'],
        }

        ########### Группируем ###########

        # Ограничения сотрудников
        constraints = {}
        for worker_constraint in list(WorkerConstraint.objects.select_related('employment').filter(
                employment__shop_id=shop_id)):
            key = worker_constraint.worker_id
            if key not in constraints:
                constraints[key] = []
            constraints[key].append(worker_constraint)
        work_types = {
            x.id: dict(WorkTypeConverter.convert(x), slots=[]) for x in WorkType.objects.filter(
                dttm_deleted__isnull=True,
                shop_id=shop_id,
            )
        }

        slots = Slot.objects.filter(shop_id=shop_id, work_type_id__isnull=False)
        for slot in slots:
            work_types[slot.work_type_id]['slots'].append({
                'tm_start': Converter.convert_time(slot.tm_start),
                'tm_end': Converter.convert_time(slot.tm_end),
            })

        # Информация по кассам для каждого сотрудника
        need_work_types = WorkType.objects.filter(shop_id=shop_id).values_list('id', flat=True)
        worker_cashbox_info = {}
        for worker_cashbox_inf in list \
                    (EmploymentWorkType.objects.select_related('employment').filter(work_type_id__in=need_work_types,
                                                                                    is_active=True)):
            key = worker_cashbox_inf.employment.user_id
            if key not in worker_cashbox_info:
                worker_cashbox_info[key] = []
            worker_cashbox_info[key].append(worker_cashbox_inf)

        # Уже составленное расписание
        worker_day = {}
        for worker_d in new_worker_days:
            key = worker_d.worker_id
            if key not in worker_day:
                worker_day[key] = []
            worker_day[key].append(worker_d)

        # Расписание за прошлую неделю от даты составления
        prev_data = {}
        for worker_d in prev_worker_days:
            key = worker_d.worker_id
            if key not in prev_data:
                prev_data[key] = []
            prev_data[key].append(worker_d)

        employment_stat_dict = count_prev_paid_days(dt_from - timedelta(days=1), employments, shop.region_id)
        # month_stat = count_work_month_stats(shop, dt_first, dt_from, Employment.objects.filter(user_id__in=user_ids))

        ##################################################################

        # если стоит флаг shop.paired_weekday, смотрим по юзерам, нужны ли им в этом месяце выходные в выходные
        resting_states_list = [WorkerDay.TYPE_HOLIDAY]
        if shop.settings.paired_weekday:
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
        dates = [dt_from + timedelta(days=i) for i in range((dt_to - dt_from).days)]
        for employment in employments:
            # Для уволенных сотрудников
            if employment.dt_fired:
                workers_month_days = worker_day.get(employment.user_id,
                                                    [])  # Может случиться так что для этого работника еще никаким образом расписание не составлялось
                workers_month_days.sort(key=lambda wd: wd.dt)
                workers_month_days_new = []
                wd_index = 0
                for dt in dates:
                    if (workers_month_days[wd_index].dt if \
                            wd_index < len(
                                workers_month_days) else None) and dt < employment.dt_fired:  # Если вернется пустой список, нужно исключать ошибку out of range
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
                workers_month_days = worker_day.get(employment.user_id,
                                                    [])  # Может случиться так что для этого работника еще никаким образом расписание не составлялось
                workers_month_days.sort(key=lambda wd: wd.dt)
                workers_month_days_new = []
                wd_index = 0
                for dt in dates:
                    if (workers_month_days[wd_index].dt if \
                            wd_index < len(
                                workers_month_days) else None) == dt:  # Если вернется пустой список, нужно исключать ошибку out of range
                        workers_month_days_new.append(workers_month_days[wd_index])
                        wd_index += 1
                    else:
                        workers_month_days_new.append(WorkerDay(
                            type=WorkerDay.TYPE_HOLIDAY,
                            dt=dt,
                            worker_id=employment.user_id,
                        ))
                worker_day[employment.user_id] = workers_month_days_new
            if employment.dt_hired > dt_from:
                workers_month_days = worker_day.get(employment.user_id, [])
                workers_month_days.sort(key=lambda wd: wd.dt)
                workers_month_days_new = []
                wd_index = 0
                user_dt = dt_from
                while user_dt != employment.dt_hired:
                    workers_month_days_new.append(WorkerDay(
                        type=WorkerDay.TYPE_HOLIDAY,
                        dt=user_dt,
                        worker_id=employment.user_id,
                    ))
                    user_dt = user_dt + timedelta(days=1)
                user_dt = employment.dt_hired
                while user_dt <= dt_to:
                    if (workers_month_days[wd_index].dt if \
                            wd_index < len(workers_month_days) else None) == user_dt:
                        workers_month_days_new.append(workers_month_days[wd_index])
                        wd_index += 1
                    user_dt = user_dt + timedelta(days=1)

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
            clients=Sum(F('value') / period_step * (1.0 + (shop.settings.absenteeism / 100)))
        ).values_list(
            'dttm_forecast',
            'operation_type__work_type_id',
            'clients'
        )

        demands = [{
            'dttm_forecast': Converter.convert_datetime(x[0]),
            'work_type': x[1],
            'clients': x[2],
        } for x in periods]

        # Параметры инициализации
        init_params = json.loads(shop.settings.init_params)
        work_days = list(ProductionDay.objects.filter(
            dt__gte=dt_first,
            dt__lt=dt_to,
            type__in=ProductionDay.WORK_TYPES,
            region_id=shop.region_id,
        ))
        work_hours = sum(
            [
                ProductionDay.WORK_NORM_HOURS[wd.type]
                for wd in work_days
            ]
        )  # норма рабочего времени за оставшийся период период (за месяц)
        work_hours = shop.settings.fot if shop.settings.fot else work_hours  # fixme: tmp, special for 585
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
                    'constraints_info': [{
                        'id': obj.id,
                        'worker': obj.worker_id,
                        'week_length': obj.employment.week_availability,
                        'weekday': obj.weekday,
                        'tm': Converter.convert_time(obj.tm),
                        'is_lite': obj.is_lite,
                    } for obj in constraints.get(e.user_id, [])],
                    #     Converter.convert(
                    #     constraints.get(e.user_id, []),
                    #     WorkerConstraint,
                    #     fields=['id', 'worker_id', 'employment__week_availability', 'weekday', 'tm', 'is_lite'], #change algo worker -> worker_id
                    #     out_array=True,
                    # ),
                    'availability_info': Converter.convert(
                        availabilities.get(e.user_id, []),
                        UserWeekdaySlot,
                        fields=['id', 'worker_id', 'employment__week_availability', 'weekday', 'slot', 'is_sutable'],
                        # change algo worker -> worker_id
                        custom_converters={
                            'slot': lambda obj: {
                                'id': obj.id,
                                'shop': obj.shop_id,
                                'tm_start': Converter.convert_time(obj.tm_start),
                                'tm_end': Converter.convert_time(obj.tm_end),
                                'name': obj.name
                            }
                        },
                        out_array=True,
                    ),
                    'worker_cashbox_info': [{
                        'id': obj.id,
                        'worker': obj.employment.user_id,
                        'work_type': obj.work_type_id,
                        'mean_speed': obj.mean_speed,
                        'bills_amount': obj.bills_amount,
                        'period': obj.period,
                        'priority': obj.priority,
                        'duration': obj.duration
                    } for obj in worker_cashbox_info.get(e.user_id, [])
                    ],
                    # Converter.convert(
                    #     worker_cashbox_info.get(e.user_id, []),
                    #     WorkerCashboxInfo,
                    #     fields=['id', 'employment__user_id', 'work_type', 'mean_speed', 'bills_amount', 'priority', 'duration'],  # change algo worker -> employment__user_id work_type -> work_type_id
                    #     out_array=True,
                    # ),
                    'workdays': WorkerDayConverter.convert(worker_day.get(e.user_id, []), out_array=True),
                    'prev_data': WorkerDayConverter.convert(prev_data.get(e.user_id, []), out_array=True),
                    'overworking_hours': employment_stat_dict[e.id].get('diff_prev_paid_hours', 0),
                    'overworking_days': employment_stat_dict[e.id].get('diff_prev_paid_days', 0),
                    'norm_work_amount': (work_hours - employment_stat_dict[e.id]['paid_hours'] -
                                         employment_stat_dict[e.id]['vacations'] * ProductionDay.WORK_NORM_HOURS[
                                             ProductionDay.TYPE_WORK]
                                         ) * e.norm_work_hours / 100,
                    'required_coupled_hol_in_hol': employment_stat_dict[e.id].get('required_coupled_hol_in_hol', 0),
                    'min_shift_len': e.shift_hours_length_min if e.shift_hours_length_min else 0,
                    'max_shift_len': e.shift_hours_length_max if e.shift_hours_length_max else 24,
                    'min_time_between_slots': e.min_time_btw_shifts if e.min_time_btw_shifts else 0,
                    'is_dm': get_position_status(e),
                    'dt_new_week_availability_from': Converter.convert_date(e.dt_new_week_availability_from),
                }
                for e in employments
            ],
            'algo_params': {
                'min_add_coef': shop.mean_queue_length,
                'cost_weights': json.loads(shop.settings.cost_weights),
                'method_params': json.loads(shop.settings.method_params),
                'breaks_triplets': json.loads(shop.settings.break_triplets),
                'init_params': init_params,
            },
        }

        tt.save()
        data = json.dumps(data).encode('ascii')
        try:
            r = requests.post('http://{}/'.format(settings.TIMETABLE_IP), data=data)
            res = r.json()

            tt.task_id = res.get('task_id', '')
            if tt.task_id is None:
                tt.status = ShopMonthStat.ERROR
                tt.save()
        except Exception as e:

            print(e)
            tt.status = ShopMonthStat.ERROR

            tt.status_message = str(e)
            tt.save()
            raise MessageError('tt_server_error')

        return Response()


    @action(detail=False, methods=['post', 'get'], authentication_classes=[TokenAuthentication])
    def set_timetable(self, request):
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
        form = request.data

        try:
            data = json.loads(form['data'])
        except:
            raise ValidationError('cannot parse json')

        timetable = ShopMonthStat.objects.get(id=form['timetable_id'])

        shop = timetable.shop
        break_triplets = json.loads(shop.settings.break_triplets)

        timetable.status = data['timetable_status']
        timetable.status_message = data.get('status_message', False)
        timetable.save()
        if timetable.status != ShopMonthStat.READY and timetable.status_message:
            return Response(timetable.status_message)

        if data['users']:
            for uid, v in data['users'].items():
                uid = int(uid)
                for wd in v['workdays']:
                    # todo: actually use a form here is better
                    # todo: too much request to db

                    dt = Converter.parse_date(wd['dt'])
                    wd_obj = WorkerDay(
                        is_approved=False,
                        is_fact=False,
                        dt=dt,
                        worker_id=uid,
                        type=wd['type']
                    )

                    wdays = {w.is_approved: w for w in WorkerDay.objects.filter(
                        Q(shop=shop) | Q(shop__isnull=True),
                        is_fact=False,
                        worker_id=uid,
                        dt=dt,
                    )}

                    #неподтвержденная версия
                    if False in wdays:
                        wd_obj=wdays[False]
                        wd_obj.type=wd['type']
                        WorkerDayCashboxDetails.objects.filter(worker_day=wd_obj).delete()
                    elif True in wdays:
                        wd_obj.parent_worker_day=wdays[True]

                    if wd['type'] == WorkerDay.TYPE_WORKDAY:
                        wd_obj.shop=shop

                    if WorkerDay.is_type_with_tm_range(wd_obj.type):
                        wd_obj.dttm_work_start = Converter.parse_datetime(wd['dttm_work_start'])
                        wd_obj.dttm_work_end = Converter.parse_datetime(wd['dttm_work_end'])
                        wd_obj.work_hours = WorkerDay.count_work_hours(break_triplets, wd_obj.dttm_work_start, wd_obj.dttm_work_end)
                        wd_obj.save()

                        wdd_list = []

                        for wdd in wd['details']:
                            wdd_el = WorkerDayCashboxDetails(
                                worker_day=wd_obj,
                                dttm_from=Converter.parse_datetime(wdd['dttm_from']),
                                dttm_to=Converter.parse_datetime(wdd['dttm_to']),
                            )
                            if wdd['type'] > 0:
                                wdd_el.work_type_id = wdd['type']
                            else:
                                wdd_el.status = WorkerDayCashboxDetails.TYPE_BREAK

                            wdd_list.append(wdd_el)
                        WorkerDayCashboxDetails.objects.bulk_create(wdd_list)

                    else:
                        wd_obj.dttm_work_start = None
                        wd_obj.dttm_work_end = None
                        wd_obj.work_hours = timedelta(hours=0)
                        wd_obj.shop=None
                        wd_obj.save()


            for work_type in shop.worktype_set.all():
                cancel_shop_vacancies.apply_async((shop.id, work_type.id))
                create_shop_vacancies_and_notify.apply_async((shop.id, work_type.id))

        return Response({})

    @action(detail=False, methods=['post', 'get'])
    def delete_timetable(self, request):
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
        serializer = AutoSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        form = serializer.validated_data

        shop_id = form['shop_id']

        dt_from = form['dt_from']
        dt_to = form['dt_to']

        dt_min = datetime.now().date() + timedelta(days=REBUILD_TIMETABLE_MIN_DELTA)

        if dt_from < dt_min:
            raise MessageError("tt_delete_past")

        dt_first = dt_from.replace(day=1)

        tts = ShopMonthStat.objects.filter(shop_id=shop_id, dt=dt_first)
        for tt in tts:
            if (tt.status == ShopMonthStat.PROCESSING) and (not tt.task_id is None):
                try:
                    requests.post(
                        'http://{}/delete_task'.format(settings.TIMETABLE_IP), data=json.dumps({'id': tt.task_id}).encode('ascii')
                    )
                except (requests.ConnectionError, requests.ConnectTimeout):
                    pass
                # send_notification('D', tt, sender=request.user)
        tts.update(status=ShopMonthStat.NOT_DONE)

        user_ids=Employment.objects.get_active(
            dt_from=dt_from,
            dt_to=dt_to,
            shop_id=shop_id,
            auto_timetable=True
        ).values('user_id')

        # Not approved
        wdays = WorkerDay.objects.filter(
            Q(shop_id=shop_id) | Q(shop_id__isnull=True),
            dt__gte=dt_from,
            dt__lt=dt_to,
            worker_id__in=user_ids,
            is_approved=False,
            # is_vacancy=False,
            created_by__isnull=True,
        )

        WorkerDayCashboxDetails.objects.filter(
            worker_day__in=wdays,
        ).delete()

        wdays.filter(
            parent_worker_day__isnull=True
        ).delete()

        wdays.update(
            dttm_work_start=None,
            dttm_work_end=None,
            #worker_id=None, TODO: ???
            type=WorkerDay.TYPE_EMPTY

        )

        # approved
        wdays = WorkerDay.objects.filter(
            Q(shop_id=shop_id) | Q(shop_id__isnull=True),
            dt__gte=dt_from,
            dt__lt=dt_to,
            worker_id__in=user_ids,
            is_approved=True,
            # is_vacancy=False,
            created_by__isnull=True,
            child__isnull=True
        )
        WorkerDay.objects.bulk_create(
            [WorkerDay(
                # worker_id=w.worker_id, TODO: ???
                type=WorkerDay.TYPE_EMPTY,
                dt=w.dt,
                parent_worker_day=w
            ) for w in wdays]
        )

        # # cancel vacancy
        # # todo: add deleting workerdays
        # work_type_ids = [w.id for w in WorkType.objects.filter(shop_id=shop_id)]
        # WorkerDayCashboxDetails.objects.filter(
        #     dttm_from__date__gte=dt_from,
        #     dttm_from__date__lt=dt_to,
        #     is_vacancy=True,
        #     work_type_id__in=work_type_ids,
        # ).update(
        #     dttm_deleted=timezone.now(),
        #     status=WorkerDayCashboxDetails.TYPE_DELETED,
        # )

        return Response()

def count_prev_paid_days(dt_end, employments, region_id, dt_start=None):
    """
    Функция для подсчета разница между нормальным количеством отработанных дней и часов и фактическими

    Args:
        dt_start(datetime.date):
        dt_end(datetime.date):
        employments(QuerySet):

    Returns:
        (dict): словарь с id'шниками пользователей -- по ключам, и 'diff_prev_paid_days' и 'diff_prev_paid_hours' \
        -- по значениям
    """

    dt_start = dt_start if dt_start else date(dt_end.year, 1, 1)

    prod_cal = CalendarPaidDays(dt_start, dt_end, region_id)
    ids = [e.id for e in employments]

    prev_info = list(Employment.objects.filter(
        Q(
          Q(user__worker_day__type__in=WorkerDay.TYPES_PAID)|
          Q(user__worker_day__type=WorkerDay.TYPE_VACATION),
          user__worker_day__dt__gte=dt_start,
          user__worker_day__dt__lt=dt_end,
          user__worker_day__is_fact=False,
          user__worker_day__is_approved=True) |
        Q(user__worker_day=None),  # for doing left join
        id__in=ids,
    ).values('id').annotate(
        paid_days=Coalesce(Count('user__worker_day', filter=Q(user__worker_day__type__in=WorkerDay.TYPES_PAID)), 0),
        paid_hours=Coalesce(Sum(Extract(F('user__worker_day__work_hours'),'epoch') / 3600, filter=Q(user__worker_day__type__in=WorkerDay.TYPES_PAID)), 0),
        vacations=Coalesce(Count('user__worker_day', filter=Q(user__worker_day__type=WorkerDay.TYPE_SELF_VACATION)), 0),
    ).order_by('id'))
    prev_info = {e['id']: e for e in prev_info}
    employment_stat_dict = {}

    for employment in employments:
        dt_u_st = employment.dt_hired if employment.dt_hired and (employment.dt_hired > dt_start) else dt_start

        paid_days_n_hours_prev = prod_cal.paid_days(dt_u_st, dt_end, employment)

        employment_stat_dict[employment.id] = {
            'overworking_days': paid_days_n_hours_prev['days'],
            'overworking_hours': paid_days_n_hours_prev['hours'],
            'paid_days': 0,
            'paid_hours': 0,
            'vacations': 0,
        }

        if prev_info.get(employment.id, None):
            employment_stat_dict[employment.id]['overworking_days'] += prev_info[employment.id]['paid_days']
            employment_stat_dict[employment.id]['overworking_hours'] += prev_info[employment.id]['paid_hours']
            employment_stat_dict[employment.id]['paid_days'] = prev_info[employment.id]['paid_days']
            employment_stat_dict[employment.id]['paid_hours'] = prev_info[employment.id]['paid_hours']
            employment_stat_dict[employment.id]['vacations'] = prev_info[employment.id]['vacations']


    return employment_stat_dict
