import json
import logging
from datetime import datetime, timedelta, date

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import F, Count, Sum, Q
from django.db.models.functions import Coalesce, Extract
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from src.base.models import Shop, Employment, ProductionDay, ShopSettings, WorkerPosition, Employee
from src.base.permissions import Permission
from src.forecast.models import PeriodClients
from src.timetable.auto_settings.serializers import (
    AutoSettingsCreateSerializer,
    AutoSettingsDeleteSerializer,
    AutoSettingsSetSerializer,
)
from src.timetable.models import (
    ShopMonthStat,
    WorkType,
    WorkerConstraint,
    EmploymentWorkType,
    WorkerDay,
    Slot,
    UserWeekdaySlot,
    WorkerDayType,
)
from src.timetable.vacancy.tasks import create_shop_vacancies_and_notify, cancel_shop_vacancies
from src.timetable.worker_day.stat import CalendarPaidDays, WorkersStatsGetter
from src.util.models_converter import (
    WorkTypeConverter,
    EmploymentConverter,
    WorkerDayConverter,
    Converter,
)

algo_set_timetable_logger = logging.getLogger('algo_set_timetable')


class AutoSettingsViewSet(viewsets.ViewSet):
    error_messages = {
        "tt_create_past": _("Timetable should be built at least from {num} day from now."),
        "tt_exists": _("Timetable already exists."),
        "tt_users_without_spec": _("No work type set for users: {users}."),
        "tt_period_empty": _("Not enough demand {period} for work type {work_type}."),
        "tt_user_extra_shifts": _("More than one shift are selected for worker {id} {last_name} {first_name} with fixed hours."),
        "tt_server_error": _("Fail sending data to server."),
        "tt_delete_past": _("You can't delete timetable in the past."),
        "settings_not_exists": _("You need to select auto-scheduling settings for the department."),
        "tt_different_acc_periods": _("You need to select an interval within a single accounting period."),
    }
    serializer_class = AutoSettingsCreateSerializer
    permission_classes = [Permission]
    basename = 'AutoSettings'
    openapi_tags = ['AutoSettings',]

    @swagger_auto_schema(methods=['post'], request_body=AutoSettingsCreateSerializer, responses={200:'Empty response', 400: 'Fail sending data to server.'})
    @action(detail=False, methods=['post'])
    def create_timetable(self, request):
        """
        Собирает данные в нужном формате и отправляет запрос на составления на алгоритмы.
        Args:
            shop_id, dt_from, dt_to, is_remarking            
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

        serializer = AutoSettingsCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        form = serializer.validated_data

        shop_id = form['shop_id']
        dt_from = form['dt_from']
        dt_to = form['dt_to']

        if not (self.request.user.network.get_acc_period_range(dt_to) == self.request.user.network.get_acc_period_range(dt_from)):
            raise ValidationError(self.error_messages["tt_different_acc_periods"])

        dt_min = datetime.now().date() + timedelta(days=settings.REBUILD_TIMETABLE_MIN_DELTA)

        if dt_from < dt_min:
            raise ValidationError(self.error_messages["tt_create_past"].format(num=settings.REBUILD_TIMETABLE_MIN_DELTA))

        dt_first = dt_from.replace(day=1)

        tt, _ = ShopMonthStat.objects.get_or_create(shop_id=shop_id, dt=dt_first, defaults={'dttm_status_change': timezone.now()})
        if tt.status is ShopMonthStat.NOT_DONE:
            tt.status = ShopMonthStat.PROCESSING
            tt.dttm_status_change = timezone.now()
            tt.save()
        elif (form['is_remaking']):
            tt.status = ShopMonthStat.PROCESSING
            tt.dttm_status_change = datetime.now()
            tt.save()
        else:
            raise ValidationError(self.error_messages["tt_exists"])

        shop = Shop.objects.get(id=shop_id)

        if shop.settings_id is None:
            raise ValidationError(self.error_messages["settings_not_exists"])

        employments = Employment.objects.get_active(
            shop.network_id,
            dt_from=dt_from,
            dt_to=dt_to,
            shop_id=shop_id,
            is_visible=True,
            # auto_timetable=True, чтобы все сотрудники были, так как пересоставляем иногда для 1
        ).select_related('employee__user', 'position')

        employee_ids = employments.values_list('employee_id', flat=True)

        worker_stats_cls = WorkersStatsGetter(
            shop_id=shop_id,
            dt_from=dt_from,
            dt_to=dt_to,
            employee_id__in=list(employee_ids),
        )
        stats = worker_stats_cls.run()

        employees = Employee.objects.filter(id__in=employee_ids)
        employees_dict = {e.id: e for e in employees}

        period_step = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute

        ########### Проверки ###########

        # проверка что у всех юзеров указаны специализации
        users_without_spec = []
        for employment in employments:
            employment_work_type = EmploymentWorkType.objects.filter(
                employment=employment,
                is_active=True
            )
            if not employment_work_type.exists():
                users_without_spec.append(employment.employee.user.first_name + ' ' + employment.employee.user.last_name)
        if users_without_spec:
            tt.status = ShopMonthStat.NOT_DONE
            tt.save()
            raise ValidationError(
                self.error_messages["tt_users_without_spec"].format(users=', '.join(users_without_spec)))

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
        #         dttm_forecast__date__lte=dt_to,
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
            key = user_weekday_slot.employee_id
            if key not in availabilities:
                availabilities[key] = []
            availabilities[key].append(user_weekday_slot)
        for employment in employments:
            employee_id = employment.employee_id
            employee = employees_dict[employee_id]
            if employment.is_fixed_hours:
                availability_info = availabilities.get(employee_id, [])
                if not (len(availability_info)):
                    print(f'Warning! User {employee.user_id} {employee.user.last_name} {employee.user.first_name} with fixed hours, '
                          f'but he does not have a set of shifts he can work on!'.encode('utf-8'))
                mask = [0 for _ in range(len(availability_info))]
                for info_day in availability_info:
                    mask[info_day.weekday] += 1
                if mask.count(1) != len(mask):
                    tt.delete()
                    raise ValidationError(self.error_messages['tt_user_extra_shifts'].format(
                        id=employee.user.id, last_name=employee.user.last_name, first_name=employee.user.first_name))


        ##################################################################

        # Функция для заполнения расписания
        def fill_wd_array(worker_days_db, array, prev_data=False):
            worker_days_mask = {}
            for wd in worker_days_db:
                if ((wd['id'] in worker_days_mask) and wd['work_types__id']) or \
                        ((prev_data is False) and (wd['type_id'] == WorkerDay.TYPE_HOLIDAY) and (
                                wd['created_by_id'] is None)):
                    continue

                worker_days_mask[wd['id']] = len(array)
                wd_mod = WorkerDay(
                    id=wd['id'],
                    type_id=wd['type_id'],
                    dttm_added=wd['dttm_added'],
                    dt=wd['dt'],
                    employee_id=wd['employee_id'],
                    dttm_work_start=wd['dttm_work_start'],
                    dttm_work_end=wd['dttm_work_end'],
                    created_by_id=wd['created_by_id'],
                    shop_id=wd.get('shop_id'),
                )
                wd_mod.work_type_id = wd['work_types__id'] if wd['work_types__id'] else None
                array.append(wd_mod)

        base_wd_qs = WorkerDay.objects.filter(
            employee_id__in=employee_ids,
            is_fact=False,
            is_approved=not form['use_not_approved'],
        ).exclude(
            type_id=WorkerDay.TYPE_EMPTY,
        ).order_by(
            'dt', 'employee_id'
        ).values(
            'id',
            'type_id',
            'dttm_added',
            'dt',
            'employee_id',
            'dttm_work_start',
            'dttm_work_end',
            'work_types__id',
            'created_by_id',
            'shop_id',
        )
        new_worker_days = []
        worker_days_db = base_wd_qs.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
        )
        fill_wd_array(worker_days_db, new_worker_days, prev_data=form.get('is_remaking', False))

        prev_worker_days = []
        worker_days_db = base_wd_qs.filter(
            dt__gte=dt_from - timedelta(days=7),
            dt__lt=dt_from,  # не должны попадать дни за начало периода
        )
        fill_wd_array(worker_days_db, prev_worker_days, prev_data=True)

        max_work_coef = 1
        min_work_coef = 1
        if shop.settings.process_type == ShopSettings.YEAR_NORM:
            max_work_coef += shop.settings.more_norm / 100
            min_work_coef -= shop.settings.less_norm / 100
        method_params = json.loads(shop.settings.method_params)

        shop_dict = {
            'shop_name': shop.name,
            'process_type': shop.settings.process_type,
            'mean_queue_length': shop.mean_queue_length,
            'max_queue_length': shop.max_queue_length,
            'dead_time_part': shop.dead_time_part,
            'max_work_coef': max_work_coef,
            'min_work_coef': min_work_coef,
            'period_step': period_step,
            'tm_start_work': shop.open_times,
            'tm_end_work': shop.close_times,
            'work_schedule': shop.get_work_schedule(dt_from, dt_to),
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
            'use_multiple_work_types': method_params[0].get('use_multiple_work_types', False) if len(method_params) else False,
        }

        ########### Группируем ###########

        # Ограничения сотрудников
        constraints = {}
        for worker_constraint in list(WorkerConstraint.objects.select_related('employment').filter(
                employment__in=employments)):
            key = worker_constraint.employment_id  # TODO: покрыть тестами
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
                                                                                    employment__in=employments,
                                                                                    is_active=True)):
            key = worker_cashbox_inf.employment.employee_id
            if key not in worker_cashbox_info:
                worker_cashbox_info[key] = []
            worker_cashbox_info[key].append(worker_cashbox_inf)

        # Уже составленное расписание
        worker_day = {}
        for worker_d in new_worker_days:
            # дни отработанные в других отделах
            if worker_d.shop_id and worker_d.shop_id != shop_id:
                worker_d.type_id = 'R'

            key = worker_d.employee_id
            worker_day.setdefault(key, []).append(worker_d)

        # Расписание за прошлую неделю от даты составления
        prev_data = {}
        for worker_d in prev_worker_days:
            key = worker_d.employee_id
            prev_data.setdefault(key, []).append(worker_d)

        employment_stat_dict = count_prev_paid_days(dt_from - timedelta(days=1), employments, shop.region_id)
        # month_stat = count_prev_paid_days(dt_to + timedelta(days=1), employments, shop.region_id, dt_start=dt_from, is_approved=not form['use_not_approved'])
        # month_stat_prev = count_prev_paid_days(dt_from, employments, shop.region_id, dt_start=dt_first, is_approved=not form['use_not_approved'])

        ##################################################################

        # если стоит флаг shop.paired_weekday, смотрим по юзерам, нужны ли им в этом месяце выходные в выходные
        resting_states_list = [WorkerDay.TYPE_HOLIDAY]
        if shop.settings.paired_weekday:
            for employment in employments:
                coupled_weekdays = 0
                month_info = prev_data.get(employment.employee_id, [])
                for day in range(len(month_info) - 1):
                    day_info = month_info[day]
                    if day_info.dt.weekday() == 5 and day_info.type in resting_states_list:
                        next_day_info = month_info[day + 1]
                        if next_day_info.dt.weekday() == 6 and next_day_info.type in resting_states_list:
                            coupled_weekdays += 1

                employment_stat_dict[employment.id]['required_coupled_hol_in_hol'] = 0 if coupled_weekdays else 1

        ########### Корректировка рабочих ###########
        dates = [dt_from + timedelta(days=i) for i in range((dt_to - dt_from).days + 1)]
        for employment in employments:
            # Для уволенных сотрудников
            if employment.dt_fired:
                workers_month_days = worker_day.get(employment.employee_id,
                                                    [])  # Может случиться так что для этого работника еще никаким образом расписание не составлялось
                workers_month_days.sort(key=lambda wd: wd.dt)
                workers_month_days_new = []
                wd_index = 0
                for dt in dates:
                    if (workers_month_days[wd_index].dt if \
                            wd_index < len(
                                workers_month_days) else None) == dt and dt <= employment.dt_fired:  # Если вернется пустой список, нужно исключать ошибку out of range
                        workers_month_days_new.append(workers_month_days[wd_index])
                        wd_index += 1
                    elif dt <= employment.dt_fired and employment.auto_timetable:
                        continue
                    else:
                        workers_month_days_new.append(WorkerDay(
                            type_id=WorkerDay.TYPE_HOLIDAY,
                            dt=dt,
                            employee_id=employment.employee_id,
                        )
                        )
                worker_day[employment.employee_id] = workers_month_days_new
                # Если для сотрудника не составляем расписание, его все равно нужно учитывать, так как он покрывает спрос
            # Реализация через фиксированных сотрудников, чтобы не повторять функционал
            elif not employment.auto_timetable:
                employment.is_fixed_hours = True
                # Может случиться так что для этого работника еще никаким образом расписание не составлялось
                workers_month_days = worker_day.get(employment.employee_id, [])
                workers_month_days.sort(key=lambda wd: wd.dt)
                workers_month_days_new = []
                wd_index = 0
                for dt in dates:
                    if (workers_month_days[wd_index].dt if wd_index < len(workers_month_days) else None) == dt:
                        # Если вернется пустой список, нужно исключать ошибку out of range
                        workers_month_days_new.append(workers_month_days[wd_index])
                        wd_index += 1
                    else:
                        workers_month_days_new.append(WorkerDay(
                            type_id=WorkerDay.TYPE_HOLIDAY,
                            dt=dt,
                            employee_id=employment.employee_id,
                        ))
                worker_day[employment.employee_id] = workers_month_days_new
            if employment.dt_hired > dt_from:
                workers_month_days = worker_day.get(employment.employee_id, [])
                workers_month_days.sort(key=lambda wd: wd.dt)
                workers_month_days_new = []
                wd_index = 0
                user_dt = dt_from
                while user_dt != employment.dt_hired:
                    workers_month_days_new.append(WorkerDay(
                        type_id=WorkerDay.TYPE_HOLIDAY,
                        dt=user_dt,
                        employee_id=employment.employee_id,
                    ))
                    user_dt = user_dt + timedelta(days=1)
                user_dt = employment.dt_hired
                while user_dt <= dt_to:
                    if (workers_month_days[wd_index].dt if \
                            wd_index < len(workers_month_days) else None) == user_dt:
                        workers_month_days_new.append(workers_month_days[wd_index])
                        wd_index += 1
                    user_dt = user_dt + timedelta(days=1)

                worker_day[employment.employee_id] = workers_month_days_new
        ##################################################################

        ########### Выборки из базы данных ###########

        # Спрос

        absenteeism_coef = shop.settings.absenteeism if shop.settings else 0
        periods = PeriodClients.objects.shop_times_filter(
            shop,
            dt_from=dt_from,
            dt_to=dt_to,
            operation_type__dttm_deleted__isnull=True,
            operation_type__work_type__shop_id=shop_id,
            operation_type__work_type__dttm_deleted__isnull=True,
            type=PeriodClients.LONG_FORECASE_TYPE,
            dttm_forecast__date__gte=dt_from,
            dttm_forecast__date__lte=dt_to,
        ).values(
            'dttm_forecast',
            'operation_type__work_type_id',
        ).annotate(
            clients=Sum(F('value') * (1.0 + (absenteeism_coef / 100)))
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
            dt__lte=dt_to,
            type__in=ProductionDay.WORK_TYPES,
            region_id=shop.region_id,
        ))
        init_params['n_working_days_optimal'] = len(work_days)
        days_in_month = ((dt_first + relativedelta(day=31)) - dt_first).days + 1

        for e in employments:
            norm_work_amount = shop.settings.norm_hours_coeff * stats[e.employee_id]['employments'][e.id][
                'sawh_hours_plan_not_approved_selected_period' if form[
                    'use_not_approved'] else 'sawh_hours_plan_approved_selected_period']
            employment_stat_dict[e.id]['norm_work_amount'] = norm_work_amount

        ##################################################################
        breaks = {
            str(w.id): w.breaks.breaks if w.breaks else shop.settings.breaks.breaks
            for w in WorkerPosition.objects.filter(
                network_id=shop.network_id,
                id__in=employments.values_list('position_id', flat=True), # чтобы не отправлять огромный словарь перерывов
            )
        }
        breaks['default'] = shop.settings.breaks.breaks
        data = {
            'IP': settings.HOST,
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
                        'worker': obj.employment.employee_id,
                        'week_length': obj.employment.week_availability,
                        'weekday': obj.weekday,
                        'tm': Converter.convert_time(obj.tm),
                        'is_lite': obj.is_lite,
                    } for obj in constraints.get(e.id, [])],
                    #     Converter.convert(
                    #     constraints.get(e.employee_id, []),
                    #     WorkerConstraint,
                    #     fields=['id', 'employee_id', 'employment__week_availability', 'weekday', 'tm', 'is_lite'], #change algo worker -> employee_id
                    #     out_array=True,
                    # ),
                    'availability_info': Converter.convert(
                        availabilities.get(e.employee_id, []),
                        UserWeekdaySlot,
                        fields=['id', 'employee_id', 'employment__week_availability', 'weekday', 'slot', 'is_sutable'],
                        # change algo worker -> employee_id
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
                        'worker': obj.employment.employee_id,
                        'work_type': obj.work_type_id,
                        'mean_speed': obj.mean_speed,
                        'bills_amount': obj.bills_amount,
                        'period': obj.period,
                        'priority': obj.priority,
                        'duration': obj.duration
                    } for obj in worker_cashbox_info.get(e.employee_id, [])
                    ],
                    # Converter.convert(
                    #     worker_cashbox_info.get(e.employee_id, []),
                    #     WorkerCashboxInfo,
                    #     fields=['id', 'employment__employee_id', 'work_type', 'mean_speed', 'bills_amount', 'priority', 'duration'],  # change algo worker -> employment__employee_id work_type -> work_type_id
                    #     out_array=True,
                    # ),
                    'workdays': WorkerDayConverter.convert(worker_day.get(e.employee_id, []), out_array=True),
                    'prev_data': WorkerDayConverter.convert(prev_data.get(e.employee_id, []), out_array=True),
                    'overworking_hours': employment_stat_dict[e.id].get('diff_prev_paid_hours', 0),  # не учитывается
                    'overworking_days': employment_stat_dict[e.id].get('diff_prev_paid_days', 0),  # не учитывается
                    'norm_work_amount': employment_stat_dict[e.id]['norm_work_amount'],
                    'norm_work_hours': e.norm_work_hours,
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
                'method_params': method_params,
                'breaks_triplets': breaks,
                'init_params': init_params,
            },
        }

        tt.save()
        data = json.dumps(data, cls=DjangoJSONEncoder).encode('ascii')
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
            raise ValidationError(self.error_messages['tt_server_error'])

        return Response()

    @swagger_auto_schema(request_body=AutoSettingsSetSerializer, methods=['post'], responses={200: '{}', 400: 'cannot parse json'})
    @action(detail=False, methods=['post'])
    def set_timetable(self, request):
        """
        Ждет request'a от qos_algo. Когда получает, записывает данные по расписанию в бд

        Args:
            method: POST
            url: /rest_api/auto_settings/set_timetable/
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

        algo_set_timetable_logger.debug(form['data'])

        with transaction.atomic():
            timetable = ShopMonthStat.objects.get(id=form['timetable_id'])

            shop = timetable.shop
            timetable.status = data['timetable_status']
            timetable.status_message = (data.get('status_message') or '')[:256]
            timetable.save()
            if timetable.status != ShopMonthStat.READY and timetable.status_message:
                return Response(timetable.status_message)

            stats = {}
            if data['users']:
                is_dayoff_types = WorkerDayType.get_is_dayoff_types()
                dt_from = date.max
                dt_to = date.min
                for wd in list(data['users'].values())[0]['workdays']:
                    dt = Converter.parse_date(wd['dt'])
                    dt_from = dt if dt < dt_from else dt_from
                    dt_to = dt if dt > dt_to else dt_to

                employments = {
                    e.employee_id: e
                    for e in Employment.objects.get_active(
                        shop.network_id,
                        dt_from=dt_from,
                        dt_to=dt_to,
                        shop=shop,
                        is_visible=True,
                    )
                }

                plan_draft_wdays_cache = {}
                for wd in WorkerDay.objects.filter(
                            is_approved=False,
                            is_fact=False,
                            dt__gte=dt_from,
                            dt__lte=dt_to,
                            employee_id__in=data['users'].keys(),
                        ).only('id', 'employee_id', 'dt', 'shop_id', 'type_id', 'type__is_dayoff'):
                    employee_key = f'{wd.dt}_{wd.employee_id}'
                    plan_draft_wdays_cache.setdefault(employee_key, []).append(wd)

                workerdays_data = []
                for uid, v in data['users'].items():
                    uid = int(uid)
                    for wd in v['workdays']:
                        if wd['type'] == 'R':
                            continue

                        wd_data = dict(
                            is_approved=False,
                            is_fact=False,
                            dt=wd['dt'],
                            employee_id=uid,
                            type_id=wd['type'],
                            created_by_id=None,
                            last_edited_by_id=None,
                        )

                        employee_key = f'{wd["dt"]}_{uid}'
                        plan_draft_wdays = plan_draft_wdays_cache.get(employee_key)

                        if plan_draft_wdays:
                            # продпускаем даты, где есть ручные изменения
                            if any((wd.created_by_id or wd.last_edited_by_id) for wd in plan_draft_wdays):  # TODO: тест
                                continue

                            # если есть хотя бы 1 день из другого магазина, то пропускаем
                            if any((not wd.type.is_dayoff and wd.shop_id and wd.shop_id) for wd in plan_draft_wdays):
                                continue

                            # если день на дату единственный, то обновляем его, а не удаляем + создаем новый
                            if len(plan_draft_wdays) == 1:
                                wd_data['id'] = plan_draft_wdays[0].id  # чтобы обновился существующий день

                        if wd['type'] == WorkerDay.TYPE_WORKDAY:
                            wd_data['shop_id'] = shop.id
                            employment = employments.get(uid)
                            wd_data['employment_id'] = employment.id if employment else None

                            wd_details = wd.get('details', [])
                            for wdd_data in wd_details:
                                percent = wdd_data.pop('percent')
                                wdd_data['work_part'] = percent / 100
                            wd_data['worker_day_details'] = wd_details

                        if wd['type'] not in is_dayoff_types:
                            wd_data['dttm_work_start'] = Converter.parse_datetime(wd['dttm_work_start'])
                            wd_data['dttm_work_end'] = Converter.parse_datetime(wd['dttm_work_end'])
                        else:
                            wd_data['dttm_work_start'] = None
                            wd_data['dttm_work_end'] = None
                            wd_data['work_hours'] = timedelta(hours=0)
                            wd_data['shop_id'] = None
                            wd_data['employment_id'] = None

                        workerdays_data.append(wd_data)

                _objs, stats = WorkerDay.batch_update_or_create(data=workerdays_data)

                for work_type in shop.work_types.all():
                    cancel_shop_vacancies.apply_async((shop.id, work_type.id))
                    create_shop_vacancies_and_notify.apply_async((shop.id, work_type.id))

        return Response({'stats': stats})

    @swagger_auto_schema(request_body=AutoSettingsDeleteSerializer, methods=['post'], responses={200: 'empty response'})
    @action(detail=False, methods=['post'])
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
        serializer = AutoSettingsDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        form = serializer.validated_data

        shop_id = form['shop_id']

        dt_from = form['dt_from']
        dt_to = form['dt_to']

        dt_min = datetime.now().date() + timedelta(days=settings.REBUILD_TIMETABLE_MIN_DELTA)

        if dt_from < dt_min:
            raise ValidationError(self.error_messages["tt_delete_past"])

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
        shop = Shop.objects.get(id=shop_id)

        employee_ids = Employment.objects.get_active(
            shop.network_id,
            dt_from=dt_from,
            dt_to=dt_to,
            shop_id=shop_id,
            auto_timetable=True
        ).values('employee_id')

        created_by_filter = {}
        if not form['delete_created_by']:
            created_by_filter['created_by__isnull'] = True

        # Not approved
        wdays = WorkerDay.objects.filter(
            Q(shop_id=shop_id) | Q(shop_id__isnull=True),
            dt__gte=dt_from,
            dt__lte=dt_to,
            employee_id__in=employee_ids,
            is_approved=False,
            # is_vacancy=False,
            **created_by_filter,
        )

        # WorkerDayCashboxDetails.objects.filter(
        #     worker_day__in=wdays,
        # ).delete()
        wdays.delete()

        # wdays.filter(
        #     parent_worker_day__isnull=True
        # ).delete()

        # wdays.update(
        #     dttm_work_start=None,
        #     dttm_work_end=None,
        #     #employee_id=None, TODO: ???
        #     type_id=WorkerDay.TYPE_EMPTY

        # )

        # approved
        wdays = WorkerDay.objects.filter(
            Q(shop_id=shop_id) | Q(shop_id__isnull=True),
            dt__gte=dt_from,
            dt__lte=dt_to,
            employee_id__in=employee_ids,
            is_approved=True,
            # is_vacancy=False,
            child__isnull=True,
            **created_by_filter,
        )
        # WorkerDay.objects.bulk_create(
        #     [WorkerDay(
        #         # employee_id=w.employee_id, TODO: ???
        #         type_id=WorkerDay.TYPE_EMPTY,
        #         dt=w.dt,
        #         parent_worker_day=w
        #     ) for w in wdays]
        # )

        # # cancel vacancy
        # # todo: add deleting workerdays
        # work_type_ids = [w.id for w in WorkType.objects.filter(shop_id=shop_id)]
        # WorkerDayCashboxDetails.objects.filter(
        #     dttm_from__date__gte=dt_from,
        #     dttm_from__date__lte=dt_to,
        #     is_vacancy=True,
        #     work_type_id__in=work_type_ids,
        # ).update(
        #     dttm_deleted=timezone.now(),
        #     status=WorkerDayCashboxDetails.TYPE_DELETED,
        # )

        return Response()


def count_prev_paid_days(dt_end, employments, region_id, dt_start=None, is_approved=True):
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
        #   Q(employee__worker_days__type_id__in=WorkerDay.TYPES_PAID)|
        #   Q(employee__worker_days__type__in=[WorkerDay.TYPE_SELF_VACATION, WorkerDay.TYPE_VACATION, WorkerDay.TYPE_SICK, WorkerDay.TYPE_EMPTY]),
          Q(dt_fired__isnull=False) & Q(employee__worker_days__dt__lte=F('dt_fired')) | Q(dt_fired__isnull=True), #чтобы не попали рабочие дни после увольнения
          employee__worker_days__dt__gte=dt_start,
          employee__worker_days__dt__lt=dt_end,
          employee__worker_days__is_fact=False,
          employee__worker_days__is_approved=is_approved) |
        Q(employee__worker_days=None),  # for doing left join
        id__in=ids,
    ).values('id').annotate(
        paid_days=Coalesce(Count('employee__worker_days', filter=Q(employee__worker_days__type_id__in=WorkerDay.TYPES_PAID)), 0),
        paid_hours=Coalesce(Sum(Extract(F('employee__worker_days__work_hours'),'epoch') / 3600, filter=Q(employee__worker_days__type_id__in=WorkerDay.TYPES_PAID)), 0),
        vacations=Coalesce(Count('employee__worker_days', filter=Q(employee__worker_days__type__in=[WorkerDay.TYPE_SELF_VACATION, WorkerDay.TYPE_VACATION, WorkerDay.TYPE_SICK])), 0),
        no_data=Coalesce(Count('employee__worker_days', filter=Q(employee__worker_days__type_id=WorkerDay.TYPE_EMPTY)), 0),
        all_days=Coalesce(Count('employee__worker_days'), 0),
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
            'no_data': (dt_end - dt_start).days,
        }

        if prev_info.get(employment.id, None):
            employment_stat_dict[employment.id]['overworking_days'] += prev_info[employment.id]['paid_days']
            employment_stat_dict[employment.id]['overworking_hours'] += prev_info[employment.id]['paid_hours']
            employment_stat_dict[employment.id]['paid_days'] = prev_info[employment.id]['paid_days']
            employment_stat_dict[employment.id]['paid_hours'] = prev_info[employment.id]['paid_hours']
            employment_stat_dict[employment.id]['vacations'] = prev_info[employment.id]['vacations']
            employment_stat_dict[employment.id]['no_data'] = prev_info[employment.id]['no_data'] + ((dt_end - dt_start).days - prev_info[employment.id]['all_days'])

    return employment_stat_dict
