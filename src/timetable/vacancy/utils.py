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

import json
# TODO разобраться с Event
from datetime import timedelta, datetime, time

import pandas
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q, Exists, OuterRef, Sum, Subquery, DurationField
from django.utils.timezone import now
from django.utils.translation import gettext as _

from src.base.models import (
    Employment,
    User,
    Shop,
    Event,
    Notification,
    Employee,
)
from src.events.signals import event_signal
from src.timetable.events import EMPLOYEE_VACANCY_DELETED, VACANCY_CREATED, VACANCY_DELETED
from src.conf.djconfig import (
    QOS_DATETIME_FORMAT,
    EMAIL_HOST_USER,
)
from src.timetable.exceptions import WorkTimeOverlap
from src.timetable.models import (
    ExchangeSettings,
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
    EmploymentWorkType,
    ShopMonthStat,
    VacancyBlackList,
)
from src.timetable.work_type.utils import ShopEfficiencyGetter


def create_event_and_notify(workers, **kwargs):
    notification_list = []
    event = Event.objects.create(
        **kwargs,
    )
    for worker in workers:
        notification_list.append(
            Notification(
                worker=worker,
                event=event
            )
        )
        print(f"Create notification for {worker}, {event}")
    Notification.objects.bulk_create(notification_list)


def search_candidates(vacancy, **kwargs):
    """
    :param vacancy: db.WorkerDay -- only in python, not real model in db. idea: no model until users selected for sending
    :param kwargs: dict {
        'outsource': Boolean, if True then show, добавляем аутсорс
    }
    :return:
    """
    shop = vacancy.shop
    exchange_settings = shop.get_exchange_settings()   
    if not exchange_settings.automatic_worker_select_tree_level:
        return
    parent = shop.get_ancestor_by_level_distance(exchange_settings.automatic_worker_select_tree_level)
    shops = parent.get_descendants()

    # department checks

    depart_filter = Q(shop_id__in=shops)
    worker_days = WorkerDay.objects.filter(
        employee_id=OuterRef('employee_id'),
        dttm_work_start__lte=vacancy.dttm_work_start,
        dttm_work_end__gte=vacancy.dttm_work_end,
        dt=vacancy.dt,
        type_id=WorkerDay.TYPE_WORKDAY,
        child__id__isnull=True,
    )

    # todo: add outsource

    # todo: 1. add time gap for check if different shop
    # todo: 2. add WorkerCashboxInfo check if necessary
    vacancy_dt = vacancy.dt
    employments = Employment.objects.filter(
        depart_filter,
        Q(dt_fired__isnull=True) | Q(dt_fired__gt=vacancy_dt),
        Q(dt_hired__isnull=True) | Q(dt_hired__lte=vacancy_dt),
        # is_ready_for_overworkings=True,
    )
    user_ids = list(employments.annotate(
        no_wdays=~Exists(worker_days)
    ).filter(no_wdays=True).values_list('employee__user_id', flat=True))

    user_ids = set(
        user_ids + list(employments.filter(
            shop=shop
        ).annotate(
            no_wdays=~Exists(worker_days.filter(shop=shop))
        ).filter(no_wdays=True).values_list('employee__user_id', flat=True))
    )

    return User.objects.filter(id__in=user_ids)


def search_holiday_candidate(vacancy, max_working_hours, constraints, exclude_positions=[]):
    shop = vacancy.shop
    vacancy_dt = vacancy.dt
    work_hours = vacancy.work_hours
    work_types = vacancy.work_types.all().values_list('work_type_name_id', flat=True)
    active_employment_subq = Employment.objects.filter(
        Q(dt_fired__isnull=True) | Q(dt_fired__gt=vacancy_dt),
        Q(dt_hired__isnull=True) | Q(dt_hired__lte=vacancy_dt),
        employee_id=OuterRef('pk'),
        shop__in=shop.exchange_shops.filter(dttm_deleted__isnull=True),
    ).exclude(position__in=exclude_positions)
    employees = Employee.objects.annotate(
        active_empl=Exists(active_employment_subq),
        workerdays_exists=Exists(
            WorkerDay.objects.filter(
                employee_id=OuterRef('pk'),
                type_id=WorkerDay.TYPE_HOLIDAY,
                dt=vacancy_dt,
                is_fact=False,
                is_approved=True,
                canceled=False,
            )
        ),
        work_types_exists=Exists(
            EmploymentWorkType.objects.filter(
                employment__in=OuterRef('employments'),
                work_type__work_type_name_id__in=work_types,
            )
        ),
    ).filter(
        active_empl=True,
        workerdays_exists=True,
        work_types_exists=True,
    ).annotate(
        work_hours=Subquery(WorkerDay.objects.filter(
            employee_id=OuterRef('pk'),
            dt__gte=vacancy_dt.replace(day=1),
            dt__lte=vacancy_dt.replace(day=1) + relativedelta(months=+1) - timedelta(days=1),
            type__is_work_hours=True,
            is_fact=False,
            is_approved=True,
        ).order_by().values('employee__user_id').annotate(wh=Sum('work_hours')).values('wh'), output_field=DurationField()) + work_hours,
    ).filter(
        work_hours__lte=max_working_hours,
    ).select_related('user').order_by('work_hours')
    count_of_holidays = {
        3: [],
        2: [],
        1: [],
    }
    for employee in employees:
        max_holidays = 0
        holidays_in_a_row = []
        tmp_obj = {
            'employee': employee,
            'work_days': [],
        }
        for worker_day in WorkerDay.objects.filter(
            dt__gte=vacancy_dt - timedelta(days=2),
            dt__lte=vacancy_dt + timedelta(days=2),
            employee_id=employee.id,
        ).order_by('dt'):
            if worker_day.type_id == WorkerDay.TYPE_HOLIDAY:
                max_holidays += 1
                tmp_obj['work_days'].append(True)
            else:
                holidays_in_a_row.append(max_holidays)
                max_holidays = 0
                tmp_obj['work_days'].append(False)
        holidays_in_a_row.append(max_holidays)
        max_holidays = max(holidays_in_a_row)
        if (max_holidays == 4 or max_holidays == 5):
            return employee
        count_of_holidays[max_holidays].append(tmp_obj)
    for employee in count_of_holidays[3]:
        if all(employee['work_days'][:3]) or all(employee['work_days'][2:]):
            return employee['employee']

    for employee in count_of_holidays[2]:
        hours_before = 0
        hours_after = 0
        tmp_hours = 0
        for worker_day in WorkerDay.objects.qos_current_version().filter(
            dt__gte=vacancy_dt - timedelta(days=7),
            dt__lte=vacancy_dt + timedelta(days=7),
            employee_id=employee['employee'].id,
        ).select_related('type').order_by('dt'):
            if worker_day.type.is_work_hours:
                tmp_hours += worker_day.work_hours.seconds // 3600
            else:
                if all(employee['work_days'][1:3]) and worker_day.dt + timedelta(days=1) == vacancy_dt:
                    hours_before = tmp_hours
                    tmp_hours = 0
                elif all(employee['work_days'][1:3]) and worker_day.dt == vacancy_dt:
                    continue
                elif worker_day.dt == vacancy_dt:
                    hours_before = tmp_hours
                    tmp_hours = 0
                elif worker_day.dt - timedelta(days=1) == vacancy_dt:
                    continue
                elif worker_day.dt > vacancy_dt:
                    hours_after = tmp_hours
                    break
                else:
                    tmp_hours = 0
        if tmp_hours == 0:
            hours_after = tmp_hours
        if all(employee['work_days'][1:3]) and hours_before <= constraints.get('second_day_before', 40) and hours_after <= constraints.get('second_day_after', 32) or\
            all(employee['work_days'][2:4]) and hours_before <= constraints.get('first_day_after', 32) and hours_after <= constraints.get('first_day_before', 40):
            return employee['employee']

    for employee in count_of_holidays[1]:
        hours_before = 0
        hours_after = 0
        tmp_hours = 0
        for worker_day in WorkerDay.objects.qos_current_version().filter(
            dt__gte=vacancy_dt - timedelta(days=7),
            dt__lte=vacancy_dt + timedelta(days=7),
            employee_id=employee['employee'].id,
        ).select_related('type').order_by('dt'):
            if worker_day.type.is_work_hours:
                tmp_hours += worker_day.work_hours.seconds // 3600
            else:
                if worker_day.dt == vacancy_dt:
                    hours_before = tmp_hours
                    tmp_hours = 0
                    continue
                elif worker_day.dt > vacancy_dt:
                    hours_after = tmp_hours
                    break
                else:
                    tmp_hours = 0
        if hours_before <= constraints.get('1day_before', 40) and hours_after <= constraints.get('1day_after', 40):
            return employee['employee']

    return None


def do_shift_elongation(vacancy, max_working_hours):
    '''
    :params
        vacancy - вакансия
        max_working_hours - максимальное количество рабочих часов в месяц
    :description
        Функция находит работников в этом магазине у которых:
        1. Есть рабочая смена в этот день в этом магазине
        2. Начало этой смены больше начала смены вакансии или конец
           смены меньше окончания смены вакансии
        3. Тип работы этого дня совпадает с типом работы вакансии
        4. Длина смены этого рабочего дня меньше максимальной длины смены в этом магазине
        5. Количество рабочих часов в месяц не превышает максимальноого количества
           рабочих часов с учетом смены
        Выбирается самый менее загруженный работник
        Далее выбирается его рабочий день в день вакансии
        У этого рабочего дня изменяются время начала и время окончания смены
        по следующим критериям:
        1. Если время начала смены больше времени начала вакансии, ставим
           время начала вакансии
        2. Если время окончания смены меньше времени окончания вакансии, 
           ставим время окончания вакансии
        Затем обновляем время начала и окончания WorkerDayCashboxDetails 
        связанный с этим рабочим днём
        Отменяем вакансию
        Информируем работника и магазин
    '''
    shop = vacancy.shop
    vacancy_dt = vacancy.dt
    work_hours = vacancy.work_hours
    max_shift_len = time(shop.settings.shift_end)
    work_types = vacancy.work_types.all().values_list('work_type_name_id', flat=True)
    active_employment_subq = Employment.objects.filter(
        Q(dt_fired__isnull=True) | Q(dt_fired__gt=vacancy_dt),
        Q(dt_hired__isnull=True) | Q(dt_hired__lte=vacancy_dt),
        employee_id=OuterRef('pk'),
        shop=shop,
    )
    employee = Employee.objects.annotate(
        active_empl=Exists(active_employment_subq),
        workerdays_exists=Exists(
            WorkerDay.objects.filter(
                Q(dttm_work_start__gt=vacancy.dttm_work_start) | 
                Q(dttm_work_end__lt=vacancy.dttm_work_end),
                employee=OuterRef('pk'), 
                type_id=WorkerDay.TYPE_WORKDAY,
                shop=shop,
                dt=vacancy_dt,
                work_types__work_type_name_id__in=work_types,
                work_hours__lt=max_shift_len,
                is_approved=True,
                is_fact=False,
            )
        ),
    ).filter(
        active_empl=True,
        workerdays_exists=True,
    ).annotate(
        work_hours=Subquery(WorkerDay.objects.filter(
            employee_id=OuterRef('pk'),
            dt__gte=vacancy_dt.replace(day=1),
            dt__lte=vacancy_dt.replace(day=1) + relativedelta(months=+1) - timedelta(days=1),
            type__is_work_hours=True,
            is_fact=False,
            is_approved=True,
        ).order_by().values('employee__user_id').annotate(wh=Sum('work_hours')).values('wh'), output_field=DurationField()) + work_hours,
    ).filter(
        work_hours__lte=max_working_hours,
    ).select_related('user').order_by('work_hours').first()

    if employee:
        candidate = employee
        worker_day = WorkerDay.objects.filter(
            dt=vacancy_dt,
            employee_id=candidate.id,
            is_approved=True,
            is_fact=False,
        ).first()
        dttm_work_start = vacancy.dttm_work_start if worker_day.dttm_work_start > vacancy.dttm_work_start else worker_day.dttm_work_start
        dttm_work_end = vacancy.dttm_work_end if worker_day.dttm_work_end < vacancy.dttm_work_end else worker_day.dttm_work_end
        wd, created = WorkerDay.objects.update_or_create(
            dt=vacancy_dt,
            employee_id=candidate.id,
            is_approved=False,
            is_fact=False,
            defaults={
                'dttm_work_start': dttm_work_start,
                'dttm_work_end': dttm_work_end,
                'shop_id': worker_day.shop_id,
                'type': worker_day.type,
                'employment': worker_day.employment,
            }
        )
        if created:
            WorkerDayCashboxDetails.objects.bulk_create(
                [
                    WorkerDayCashboxDetails(
                        worker_day=wd,
                        work_type_id=detail.work_type_id,
                        work_part=detail.work_part,
                    )
                    for detail in WorkerDayCashboxDetails.objects.filter(worker_day=worker_day)
                ]
            )
        prev_dttm_start = worker_day.dttm_work_start
        prev_dttm_end = worker_day.dttm_work_end
        cancel_vacancy(vacancy.id)
        print(
            f'shift elongation: vacancy {vacancy}, '
            f'{worker_day.dt}, prev {prev_dttm_start}-{prev_dttm_end}, '
            f'new {wd.dttm_work_start}-{wd.dttm_work_end}, '
            f'worker {candidate.user.first_name} {candidate.user.last_name} '
        )
        create_event_and_notify(
            [candidate.user], 
            shop=shop,
            type='shift_elongation',
            params={'worker_day':wd},
        )
        if (worker_day.shop.email):
            message = f'Это автоматическое уведомление для {worker_day.shop.name} об изменениях в графике:\n\n' + \
                    f'У сотрудника {candidate.user.last_name} {candidate.user.first_name} изменено время работы. ' +\
                    f'Новое время работы с {wd.dttm_work_start} до {wd.dttm_work_end}, дата {wd.dt}.\n\n' +\
                    f'Посмотреть детали можно по ссылке: http://{settings.DOMAIN}'
            msg = EmailMultiAlternatives(
                subject='Изменение в графике выхода сотрудников',
                body=message,
                from_email=EMAIL_HOST_USER,
                to=[worker_day.shop.email,],
            )
            msg.send()


def cancel_vacancy(vacancy_id, auto=True):
    vacancy = WorkerDay.objects.filter(id=vacancy_id, is_vacancy=True).select_related(
        'shop', 
        'shop__director', 
        'employee', 
        'employee__user',
    ).first()
    if vacancy:
        shop = vacancy.shop
        employee = vacancy.employee
        if auto or vacancy.created_by_id:
            vacancy.delete()
        else:
            vacancy.canceled = True
            vacancy.employee = None
            vacancy.employment = None
            vacancy.save()
        if employee:
            employee_obj = employee
            employee = {
                'first_name': employee.user.first_name,
                'last_name': employee.user.last_name,
                'tabel_code': employee.tabel_code or '',
            }
            WorkerDay.objects.create(
                dt=vacancy.dt,
                employee=employee_obj,
                is_approved=vacancy.is_approved,
                is_fact=False,
                dttm_work_start=None,
                dttm_work_end=None,
                shop_id=None,
                type_id=WorkerDay.TYPE_HOLIDAY,
                employment=None,
                is_vacancy=False,
                is_outsource=False,
            )
            event_signal.send(
                sender=None,
                network_id=shop.network_id,
                event_code=EMPLOYEE_VACANCY_DELETED,
                user_author_id=None,
                shop_id=shop.id,
                context={
                    'user_id': employee_obj.user_id,
                    'dt': vacancy.dt.strftime('%Y-%m-%d'),
                    'dttm_from': vacancy.dttm_work_start.strftime('%Y-%m-%d %H:%M:%S'),
                    'dttm_to': vacancy.dttm_work_end.strftime('%Y-%m-%d %H:%M:%S'),
                    'shop_id': shop.id,
                    'shop_name': shop.name,
                    'auto': auto,
                },
            )
        if auto:
            event_signal.send(
                sender=None,
                network_id=shop.network_id,
                event_code=VACANCY_DELETED,
                user_author_id=None,
                shop_id=shop.id,
                context={
                    'director': {
                        'email': shop.director.email if shop.director else shop.email,
                        'name': shop.director.first_name if shop.director else shop.name,
                    },
                    'dt': vacancy.dt.strftime('%Y-%m-%d'),
                    'dttm_from': vacancy.dttm_work_start.strftime('%Y-%m-%d %H:%M:%S'),
                    'dttm_to': vacancy.dttm_work_end.strftime('%Y-%m-%d %H:%M:%S'),
                    'shop_id': shop.id,
                    'shop_name': shop.name,
                    'employee': employee,
                },
            )


def create_vacancy(dttm_from, dttm_to, shop_id, work_type_id, outsources=[]):
    is_outsource = bool(outsources)
    worker_day = WorkerDay.objects.create(
        dttm_work_start=dttm_from,
        dttm_work_end=dttm_to,
        type_id=WorkerDay.TYPE_WORKDAY,
        is_vacancy=True,
        dt=dttm_from.date(),
        shop_id=shop_id,
        is_outsource=is_outsource,
        is_approved=True, # чтобы в покрытии учитывалось при автоматическом создании вакансий
    )
    worker_day.outsources.add(*outsources)
    WorkerDayCashboxDetails.objects.create(
        work_type_id=work_type_id,
        worker_day=worker_day,  
    )
    shop = Shop.objects.get(id=shop_id)
    event_signal.send(
        sender=None,
        network_id=shop.network_id,
        event_code=VACANCY_CREATED,
        user_author_id=None,
        shop_id=shop_id,
        context={
            'director': {
                'email': shop.director.email if shop.director else shop.email,
                'name': shop.director.first_name if shop.director else shop.name,
            },
            'dt': worker_day.dt.strftime('%Y-%m-%d'),
            'dttm_from': worker_day.dttm_work_start.strftime('%Y-%m-%d %H:%M:%S'),
            'dttm_to': worker_day.dttm_work_end.strftime('%Y-%m-%d %H:%M:%S'),
            'shop_id': shop_id,
            'shop_name': shop.name,
            'work_type': WorkType.objects.select_related('work_type_name').get(id=work_type_id).work_type_name.name,
        },
    )


def confirm_vacancy(vacancy_id, user, employee_id=None, exchange=False, reconfirm=False):
    """
    :param vacancy_id:
    :param user: пользователь, откликнувшийся на вакансию
    :param exchange:
    """
    messages = {
        'no_vacancy': _('There is no such vacancy'),
        'need_symbol_for_vacancy': _('The data for the exchange of shifts is not entered. Contact the director.'),
        'cant_apply_vacancy': _('You cannot enter this vacancy.'),
        'cant_apply_vacancy_no_active_employement': _("You can't apply for this vacancy because you don't have an active employment as of the date of the vacancy."),
        'cant_apply_vacancy_not_outsource': _('You can not enter this vacancy because this vacancy is located in another network and does not imply the possibility of outsourcing.'),
        'cant_apply_vacancy_outsource_no_network': _('You cannot apply for this vacancy because this vacancy is located on another network and your network is not allowed to respond to this vacancy.'),
        'cant_apply_vacancy_outsource_not_allowed': _('You cannot apply for this vacancy because your network does not allow you to apply for an outsourced vacancy in your network.'),
        'no_timetable': _('The timetable for this period has not yet been created.'),
        'vacancy_success': _('The vacancy was successfully accepted.'),
        'cant_reconfrm_fact_exists': _("You can't reassign an employee to this vacancy, because the employee has already entered this vacancy.")
    }
    res = {
        'status_code': 200,
    }
    try:
        with transaction.atomic():
            no_employee_filter = {}
            if not reconfirm:
                no_employee_filter['employee__isnull'] = True
            vacancy = WorkerDay.objects.get_plan_approved(
                id=vacancy_id,
                is_vacancy=True,
                canceled=False,
                **no_employee_filter,
            ).select_for_update().first()
            if not vacancy:
                res['text'] = messages['no_vacancy']
                res['status_code'] = 404
                return res

            if reconfirm:
                fact = WorkerDay.objects.filter(
                    employee_id=vacancy.employee_id,
                    is_fact=True,
                    is_approved=True,
                    dt=vacancy.dt,
                )
                if fact.exists():
                    res['text'] = messages['cant_reconfrm_fact_exists']
                    res['status_code'] = 400
                    return res

            vacancy_shop = vacancy.shop

            if user.black_list_symbol is None and vacancy_shop.network.need_symbol_for_vacancy:
                res['text'] = messages['need_symbol_for_vacancy']
                res['status_code'] = 400
                return res

            shops_for_black_list = vacancy_shop.get_ancestors(include_self=True)

            if VacancyBlackList.objects.filter(symbol=user.black_list_symbol, shop__in=shops_for_black_list).exists():
                res['text'] = messages['cant_apply_vacancy']
                res['status_code'] = 400
                return res

            employee_filter = {}
            if employee_id:
                employee_filter['employee_id'] = employee_id
            else:
                employee_filter['employee__user_id'] = user.id
            active_employment = Employment.objects.get_active_empl_by_priority(
                network_id=user.network_id, dt=vacancy.dt,
                priority_shop_id=vacancy.shop_id,
                priority_work_type_id=vacancy.work_types.values_list('id', flat=True).first(),
                **employee_filter,
            ).select_related(
                'shop',
            ).first()

            # на даем откликнуться на вакансию, если нет активного трудоустройства в день вакансии
            if not active_employment:
                res['text'] = messages['cant_apply_vacancy_no_active_employement']
                res['status_code'] = 400
                return res

            # сотрудник из другой сети не может принять вакансию если это не аутсорс вакансия
            if not vacancy.is_outsource and active_employment.shop.network_id != vacancy_shop.network_id:
                res['text'] = messages['cant_apply_vacancy_not_outsource']
                res['status_code'] = 400
                return res
            # сотрудник из текущей сети не может принять аутсорс вакансию если это запрещено в сети
            elif vacancy.is_outsource and active_employment.shop.network_id == vacancy_shop.network_id and not vacancy_shop.network.allow_workers_confirm_outsource_vacancy:
                res['text'] = messages['cant_apply_vacancy_outsource_not_allowed']
                res['status_code'] = 400
                return res
            # сотрудник из другой сети не может принять вакансию если это аутсорс вакансия, но его сеть не в списке доступных
            elif vacancy.is_outsource and active_employment.shop.network_id != vacancy_shop.network_id\
                and not vacancy.outsources.filter(id=active_employment.shop.network_id).exists():
                res['text'] = messages['cant_apply_vacancy_outsource_no_network']
                res['status_code'] = 400
                return res

            employee_worker_days_qs = WorkerDay.objects.get_plan_approved(
                employee_id=active_employment.employee_id,
                dt=vacancy.dt,
            ).select_related('shop')
            employee_worker_days = list(employee_worker_days_qs)

            # нельзя откликнуться на вакансию если для сотрудника не составлен график на этот день
            if not employee_worker_days and not (
                    vacancy.is_outsource and vacancy_shop.network_id != active_employment.shop.network_id):
                res['text'] = messages['no_timetable']
                res['status_code'] = 400
                return res

            # откликаться на вакансию можно только в нерабочие/неоплачиваемые дни
            update_condition = all(
                 not wd.type.is_work_hours for wd in employee_worker_days if not wd.is_vacancy)
            if active_employment.shop_id != vacancy_shop.id and not exchange:
                try:
                    tt = ShopMonthStat.objects.get(shop=vacancy_shop, dt=vacancy.dt.replace(day=1))
                except ShopMonthStat.DoesNotExist:
                    res['text'] = messages['no_timetable']
                    res['status_code'] = 400
                    return res

                if not tt.is_approved:  # todo: добавить задержку на отклик для других магазинов
                    update_condition = False

            if update_condition or exchange:
                if any((not wd.is_vacancy and not wd.type.is_work_hours) for wd in employee_worker_days):
                    employee_worker_days_qs.filter(type__is_work_hours=False, is_vacancy=False).delete()
                elif exchange:
                    # TODO: ???
                    employee_worker_days_qs.filter(last_edited_by__isnull=True).delete()

                prev_employee_id = vacancy.employee_id
                if reconfirm and prev_employee_id:
                    # возможно надо по-другому сделать (копировать всю подтв. версию в черновик?)
                    WorkerDay.objects.filter(
                        is_fact=False,
                        is_approved=False,
                        dt=vacancy.dt,
                        employee_id=prev_employee_id,
                        is_vacancy=True,
                        dttm_work_start=vacancy.dttm_work_start,
                        dttm_work_end=vacancy.dttm_work_end,
                    ).delete()

                # TODO: проставлять сотруднику, у которого отменили вакансию, выходной,
                #  если нет других вакансий и не аутсорс?
                #  вызывать cancel_vacancy + поправить внутри логику?

                vacancy.employee = active_employment.employee
                vacancy.employment = active_employment
                vacancy.save(
                    update_fields=(
                        'employee',
                        'employment',
                    )
                )

                # TODO: тут ведь тоже надо поправить?
                WorkerDay.objects_with_excluded.filter(
                    dt=vacancy.dt,
                    employee_id=vacancy.employee_id,
                    is_fact=vacancy.is_fact,
                    is_approved=False,
                ).delete()

                vacancy_details = WorkerDayCashboxDetails.objects.filter(
                    worker_day=vacancy).values('work_type_id', 'work_part')

                try:
                    with transaction.atomic():
                        vacancy.id = None
                        vacancy.is_approved = False
                        vacancy.save()

                        WorkerDayCashboxDetails.objects.bulk_create(
                            WorkerDayCashboxDetails(
                                worker_day=vacancy,
                                work_type_id=details['work_type_id'],
                                work_part=details['work_part'],
                            ) for details in vacancy_details
                        )
                        WorkerDay.check_work_time_overlap(
                            employee_id=vacancy.employee_id, dt=vacancy.dt, is_fact=False, is_approved=False)
                except WorkTimeOverlap:
                    pass

                # TODO: создать событие об отклике на вакансию

                Event.objects.filter(worker_day=vacancy).delete()
                res['text'] = messages['vacancy_success']

                WorkerDay.check_work_time_overlap(
                    employee_id=vacancy.employee_id, dt=vacancy.dt, is_fact=False, is_approved=True)
            else:
                res['text'] = messages['cant_apply_vacancy']
                res['status_code'] = 400
    except WorkTimeOverlap as e:
        res['text'] = str(e)
        res['status_code'] = 400

    return res


def create_vacancies_and_notify(shop_id, work_type_id, dt_from=None, dt_to=None):
    """
    Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров
    """

    shop=Shop.objects.get(id=shop_id)
    exchange_settings = shop.get_exchange_settings()
    if exchange_settings is None or not exchange_settings.automatic_create_vacancies:
        return

    outsources = list(exchange_settings.outsources.all())
    tm_open_dict = shop.open_times
    tm_close_dict = shop.close_times

    if dt_from is None:
        dttm_now = now().replace(minute=0, second=0, microsecond=0)
        dttm_next_week = dttm_now + exchange_settings.automatic_check_lack_timegap

        from_dt = dttm_now.date()
        to_dt = dttm_next_week.date()

    else:
        from_dt = dt_from
        to_dt = dt_to

    params = {
        'from_dt': from_dt,
        'to_dt': to_dt,
    }

    print('check vacancies for {}; {}'.format(shop_id, work_type_id))
    params['work_type_ids'] = [work_type_id]
    shop_stat = ShopEfficiencyGetter(
        shop_id=shop_id,
        consider_vacancies=True,
        consider_canceled=True,
        **params,
    ).get()
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
        tm_shop_opens = tm_open_dict.get(str(dttm_from.weekday())) if tm_open_dict.get('all') == None else tm_open_dict.get('all')
        tm_shop_closes = tm_close_dict.get(str(dttm_from.weekday())) if tm_close_dict.get('all') == None else tm_close_dict.get('all')
        if tm_shop_opens == None or tm_shop_closes == None:
            continue

        dttm_shop_opens = datetime.combine(dttm_from.date(), tm_shop_opens)
        dttm_shop_closes = datetime.combine(dttm_from.date(), tm_shop_closes)

        if tm_shop_closes == time(hour=0, minute=0, second=0):
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
            create_vacancy(dttm_from, dttm_to, shop_id, work_type_id, outsources=outsources)


def cancel_vacancies(shop_id, work_type_id, dt_from=None, dt_to=None, approved=False):
    """
    Автоматически отменяем вакансии, в которых нет потребности
    :return:
    """
    shop = Shop.objects.get(id=shop_id)
    exchange_settings = shop.get_exchange_settings()
    if not exchange_settings or not exchange_settings.automatic_delete_vacancies:
        return

    if dt_from is None:
        from_dt = now().replace(minute=0, second=0, microsecond=0)
        to_dt = from_dt + exchange_settings.automatic_check_lack_timegap + timedelta(days=1)
        min_dttm = from_dt + exchange_settings.automatic_worker_select_timegap

        from_dt = from_dt.date()
        to_dt = to_dt.date()
    else:
        min_dttm = now().replace(minute=0, second=0, microsecond=0) + exchange_settings.automatic_worker_select_timegap
        from_dt = dt_from
        to_dt = dt_to

    params = {
        'from_dt': from_dt,
        'to_dt': to_dt,
    }

    params['work_type_ids'] = [work_type_id]
    shop_stat = ShopEfficiencyGetter(
        shop_id=shop_id,
        consider_vacancies=True,
        **params,
    ).get()
    df_stat=pandas.DataFrame(shop_stat['tt_periods']['real_cashiers']).rename({'amount':'real_cashiers'}, axis=1)
    df_stat['predict_cashier_needs'] = pandas.DataFrame(shop_stat['tt_periods']['predict_cashier_needs']).amount

    df_stat['overflow'] = df_stat.real_cashiers - df_stat.predict_cashier_needs
    df_stat['dttm'] = pandas.to_datetime(df_stat.dttm, format=QOS_DATETIME_FORMAT)
    df_stat.set_index(df_stat.dttm, inplace=True)

    vacancies = WorkerDay.objects.filter(
        (Q(employee__isnull=False) & Q(dttm_work_start__gte=min_dttm)) | Q(employee__isnull=True),
        dt__gte=from_dt,
        dt__lte=to_dt,
        work_types__id=work_type_id,
        is_vacancy=True,
        is_fact=False,
        created_by__isnull=True,
        is_approved=approved,
    ).order_by('dt', 'id')

    for vacancy in vacancies:
        cond = (df_stat['dttm'] >= vacancy.dttm_work_start) & (df_stat['dttm'] <= vacancy.dttm_work_end)
        overflow = df_stat.loc[cond,'overflow'].apply(lambda x:  x if (x < 1.0 and x >-1.0) else 1 if x >=1 else -1 ).mean()
        print ('vacancy {} overflow {}'.format(vacancy, overflow))
        lack = 1-overflow
        if lack < exchange_settings.automatic_delete_vacancy_lack_max:
            print ('cancel_vacancy overflow {} {} {}'.format(overflow, vacancy, vacancy.dttm_work_start))
            cancel_vacancy(vacancy.id)
            df_stat.loc[cond,'overflow'] -= 1


def holiday_workers_exchange():
    shops = Shop.objects.select_related('exchange_settings').filter(dttm_deleted__isnull=True)

    for shop in shops:
        exchange_settings = shop.get_exchange_settings()
        if not exchange_settings or not exchange_settings.automatic_exchange:
            continue
        max_working_hours = exchange_settings.max_working_hours
        days = max_working_hours / 24
        hours = max_working_hours % 24
        max_working_hours = timedelta(days=days, hours=hours)
        constraints = json.loads(exchange_settings.constraints)
        exclude_positions = exchange_settings.exclude_positions.all()
        dt_from = datetime.now().date() + exchange_settings.automatic_holiday_worker_select_timegap
        dt_to = dt_from + timedelta(days=1)
        vacancies = WorkerDay.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
            is_approved=True,
            shop=shop,
            is_vacancy=True,
            employee__isnull=True,
        ).select_related('shop')
        for vacancy in vacancies:
            candidate = search_holiday_candidate(vacancy, max_working_hours, constraints, exclude_positions=exclude_positions)
            if candidate:
                print(
                    f'holiday exchange: to_shop {shop.name}, '
                    f'vacancy {vacancy.work_types.first().work_type_name.name}, '
                    f'{vacancy.dt}, {vacancy.dttm_work_start}-{vacancy.dttm_work_end}, '
                    f'worker {candidate.user.first_name} {candidate.user.last_name}, '
                )
                confirm_vacancy(vacancy.id, candidate.user, employee_id=candidate.id)
                create_event_and_notify(
                    [candidate.user], 
                    type='holiday_exchange', 
                    shop=shop, 
                    params={'worker_day': vacancy, 'shop': shop}
                )


def worker_shift_elongation():
    """
    Функция для расширения смен в магазинах
    Смотрит на два дня вперед с сегодняшнего дня
    Проходится по всем вакансиям всех не удалённых магазинов
    Выполняет функцию рпасширения смены для каждой вакансии
    """
    
    shops = Shop.objects.select_related('exchange_settings').filter(dttm_deleted__isnull=True)

    for shop in shops:
        exchange_settings = shop.get_exchange_settings()
        if not exchange_settings or not exchange_settings.automatic_exchange:
            continue
        max_working_hours = exchange_settings.max_working_hours
        days = max_working_hours / 24
        hours = max_working_hours % 24
        max_working_hours = timedelta(days=days, hours=hours)
        dt_from = (now().replace(minute=0, second=0, microsecond=0) + exchange_settings.automatic_worker_select_timegap).date()
        dt_to = dt_from + exchange_settings.automatic_worker_select_timegap_to
        vacancies = WorkerDay.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
            shop=shop,
            is_approved=True,
            is_vacancy=True,
            employee__isnull=True,
        ).select_related('shop', 'shop__settings')
        for vacancy in vacancies:
            do_shift_elongation(vacancy, max_working_hours)


def workers_exchange():
    """
    Автоматически перекидываем сотрудников из других магазинов, если это приносит ценность (todo: добавить описание, что такое ценность).
    :return:
    """
    # exchange_settings_network = {
    #     e.network_id: e
    #     for e in ExchangeSettings.objects.filter(shops__isnull=True)
    # }

    shop_list = Shop.objects.select_related('exchange_settings').all()
    df_shop_stat = pandas.DataFrame()

    for shop in shop_list:
        exchange_settings = shop.get_exchange_settings()
        if not exchange_settings or not exchange_settings.automatic_exchange:
            continue
        from_dt = (now().replace(minute=0, second=0, microsecond=0) + exchange_settings.automatic_worker_select_timegap).date()
        to_dt = from_dt + exchange_settings.automatic_worker_select_timegap_to
        params = {
            'from_dt': from_dt,
            'to_dt': to_dt,
        }
        for work_type in shop.work_types.all():
            params['work_type_ids'] = [work_type.id]

            shop_stat = ShopEfficiencyGetter(
                shop.id,
                consider_vacancies=False,
                **params,
            ).get()

            df_stat=pandas.DataFrame(shop_stat['tt_periods']['real_cashiers']).rename({'amount':'real_cashiers'}, axis=1)
            df_stat['predict_cashier_needs'] = pandas.DataFrame(shop_stat['tt_periods']['predict_cashier_needs']).amount
            df_stat['lack'] = df_stat.predict_cashier_needs - df_stat.real_cashiers
            df_stat['dttm'] = pandas.to_datetime(df_stat.dttm, format=QOS_DATETIME_FORMAT)
            # df_stat['shop_id'] = shop.id
            df_stat['work_type_id'] = work_type.id
            df_shop_stat = df_shop_stat.append(df_stat)

    if not len(df_shop_stat):
        return

    df_shop_stat.set_index([# df_shop_stat.shop_id,
                            df_shop_stat.work_type_id, df_shop_stat.dttm], inplace=True)
    for shop in shop_list:
        exchange_settings = shop.get_exchange_settings()
        if not exchange_settings or not exchange_settings.automatic_exchange:
            continue
        exchange_shops = list(shop.exchange_shops.all())
        exclude_positions = exchange_settings.exclude_positions.all()
        
        for work_type in WorkType.objects.select_related('work_type_name').filter(shop_id=shop.id):

            vacancies = WorkerDay.objects.filter(
                dt__gte=from_dt,
                dt__lte=to_dt,
                work_types__id=work_type.id,
                is_vacancy=True,
                employee__isnull=True,
                is_approved=True,
            ).order_by('dt')

            for vacancy in vacancies:
                vacancy_lack = _lack_calc( df_shop_stat, work_type.id, vacancy.dttm_work_start, vacancy.dttm_work_end)
                print ('lack: {}; vacancy: {}; work_type: {}'.format(vacancy_lack, vacancy, work_type))
                dttm_from_workers = vacancy.dttm_work_start - timedelta(hours=4)
                if vacancy_lack > 0:
                    worker_days = list(WorkerDayCashboxDetails.objects.filter(
                        worker_day__dttm_work_start=vacancy.dttm_work_start,
                        worker_day__dttm_work_end=vacancy.dttm_work_end,
                        # work_type_id__in=[1],
                        work_type__shop__in=exchange_shops,
                        worker_day__is_vacancy=False,
                        worker_day__is_fact=False,
                        worker_day__is_approved=True,
                        worker_day__type__is_work_hours=True,
                        work_type__work_type_name=work_type.work_type_name,
                        worker_day__canceled=False,
                    ).exclude(
                        Q(work_type_id=work_type.id) |
                        Q(worker_day__employment__position__in=exclude_positions),
                    ).select_related('worker_day').order_by('worker_day__dt'))
                    if not len(worker_days):
                        continue
                    worker_lack = None
                    candidate_to_change = None
                    for worker_day in worker_days:
                        lack = _lack_calc(df_shop_stat, worker_day.work_type_id, worker_day.worker_day.dttm_work_start, worker_day.worker_day.dttm_work_end )
                        if worker_lack is None or lack < worker_lack:
                            worker_lack = lack
                            candidate_to_change = worker_day
                    print ('worker lack: {}; wd_detail: {}; work type: {}'.format(worker_lack, worker_day, worker_day.work_type_id))
                    if  worker_lack < -exchange_settings.automatic_worker_select_overflow_min:
                        user = candidate_to_change.worker_day.employee.user
                        print('hard exchange date {} worker_lack {} vacancy_lack {} shop_to {} shop_from {} candidate_to_change {} to vac {} user {}'.format(
                            vacancy.dt, worker_lack, vacancy_lack,
                            work_type, candidate_to_change.work_type,
                            candidate_to_change, vacancy, user
                        ))
                        shop_to = work_type.shop
                        shop_from = candidate_to_change.worker_day.shop
                        candidate_worker_day = candidate_to_change.worker_day
                        candidate_details = {
                            detail.work_type_id: detail.work_part
                            for detail in WorkerDayCashboxDetails.objects.filter(worker_day=candidate_worker_day)
                        }
                        #не удаляем candidate_to_change потому что создаем неподтвержденную вакансию
                        print(confirm_vacancy(vacancy.id, user, employee_id=candidate_to_change.worker_day.employee_id, exchange=True))
                        create_event_and_notify(
                            [user],
                            type='auto_vacancy', 
                            shop=shop_to, 
                            params={'shop': shop_to, 'vacancy': vacancy}
                        )

                        if shop_to.email:
                            message = f'Это автоматическое уведомление для {shop_to.name} об изменениях в графике:\n\n' + \
                            f'К Вам был переведён сотрудник {user.last_name} {user.first_name}, ' + \
                            f'на тип работы {work_type.work_type_name.name}, на {vacancy.dttm_work_start.time()}-{vacancy.dttm_work_end.time()}, ' + \
                            f'из магазина {shop_from.name} ({shop_from.address}), дата {vacancy.dt}.\n\n' + \
                            'Посмотреть детали можно по ссылке: http://{settings.DOMAIN}'
                            msg = EmailMultiAlternatives(
                                subject='Изменение в графике выхода сотрудников',
                                body=message,
                                from_email=EMAIL_HOST_USER,
                                to=[shop_to.email,],
                            )
                            msg.send()
                        if shop_from.email:
                            message = f'Это автоматическое уведомление для {shop_from.name} об изменениях в графике:\n\n' + \
                                f'От Вас был переведён сотрудник {user.last_name} {user.first_name}, ' + \
                                f'на тип работы {work_type.work_type_name.name}, на {vacancy.dttm_work_start.time()}-{vacancy.dttm_work_end.time()}, ' + \
                                f'в магазин {shop_to.name} ({shop_from.address}), дата {vacancy.dt}.\n\n' + \
                                'Посмотреть детали можно по ссылке: http://{settings.DOMAIN}'
                            msg = EmailMultiAlternatives(
                                subject='Изменение в графике выхода сотрудников',
                                body=message,
                                from_email=EMAIL_HOST_USER,
                                to=[shop_from.email,],
                            )
                            msg.send()

                        _lack_add(df_shop_stat, work_type.id, vacancy.dttm_work_start, vacancy.dttm_work_end, -1 )
                        for work_type_id, lack in candidate_details.items():
                            _lack_add(df_shop_stat, work_type_id, candidate_worker_day.dttm_work_start, candidate_worker_day.dttm_work_end, lack )


def _lack_add(df, work_type_id, dttm_from, dttm_to, add):
    cond = (df.work_type_id == work_type_id) & (df['dttm'] >= dttm_from) & (df['dttm'] < dttm_to)
    df.loc[cond, 'lack'] += add


def _lack_calc(df, work_type_id, dttm_from, dttm_to):
    cond = (df.work_type_id == work_type_id) & (df['dttm'] >= dttm_from) & (df['dttm'] < dttm_to)
    return df.loc[cond, 'lack'].apply(
        lambda x: x if (x < 1.0 and x > -1.0) else 1 if x >= 1 else -1
    ).mean()
