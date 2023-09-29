from django.db import models, transaction
from src.apps.base.models import Network, User
from src.apps.timetable.models import WorkerDay, WorkerDayCashboxDetails
from src.apps.timetable.worker_day.tasks import recalc_work_hours


def copy_approved(dt_from, dt_to=None):
    dt_filter = {
        'dt__gte': dt_from,
    }
    if dt_to:
        dt_filter['dt__lte'] = dt_to
    with transaction.atomic():
        not_approved_subq = WorkerDay.objects_with_excluded.filter(
            employee_id=models.OuterRef('employee_id'),
            dt=models.OuterRef('dt'),
            is_approved=False,
            is_fact=models.OuterRef('is_fact'),
        )
        worker_days_to_copy = list(WorkerDay.objects_with_excluded.filter(
            employee__isnull=False,
            **dt_filter,
        ).annotate(
            not_approved_exist=models.Exists(not_approved_subq),
        ).filter(
            not_approved_exist=False,
        ).select_related(
            'employment', 
            'employment__position',
            'employment__position__breaks',
            'shop',
            'shop__settings',
            'shop__settings__breaks',
            'shop__network',
            'shop__network__breaks',
        ).prefetch_related(
            'worker_day_details',
        ))
        wds = [
            WorkerDay(
                shop=wd.shop,
                employee_id=wd.employee_id,
                employment=wd.employment,
                work_hours=wd.work_hours,
                dttm_work_start=wd.dttm_work_start,
                dttm_work_end=wd.dttm_work_end,
                dt=wd.dt,
                is_fact=wd.is_fact,
                is_approved=False,
                type=wd.type,
                created_by_id=wd.created_by_id, # нужно ли это копировать?
                last_edited_by_id=wd.last_edited_by_id, # и это
                is_vacancy=wd.is_vacancy,
                is_outsource=wd.is_outsource,
                comment=wd.comment,
                canceled=wd.canceled,
                need_count_wh=True,
            )
            for wd in worker_days_to_copy
        ]
        wds = WorkerDay.objects.bulk_create(wds)
        search_wds = {}
        for wd in wds:
            key_employee = wd.employee_id
            search_wds.setdefault(key_employee, {}).setdefault(wd.dt, {})[wd.is_fact] = wd

        WorkerDayCashboxDetails.objects.bulk_create(
            [
                WorkerDayCashboxDetails(
                    work_part=details.work_part,
                    worker_day=search_wds[wd.employee_id][wd.dt][wd.is_fact],
                    work_type_id=details.work_type_id,
                )
                for wd in worker_days_to_copy
                for details in wd.worker_day_details.all()
            ]
        )


def copy_plan_to_fact(network_id, override_auto_start=False, override_auto_end=False, override_manual_changes_start=False, override_manual_changes_end=False, set_start=True, set_end=True, create_fact=True, extra_q=models.Q(), **kwargs):
    assert set_start or set_end
    network = Network.objects.get(id=network_id)
    last_edited_by = User.objects.get(username='qadmin')
    def _get_closest_plan(fact, plans):
        if fact.closest_plan_approved_id:
            return fact.closest_plan_approved
        if fact.dttm_work_start:
            field = 'dttm_work_start'
        else:
            field = 'dttm_work_end'
        closest_wday = sorted(
            map(
                lambda x: (abs((getattr(x, field) - getattr(fact, field)).total_seconds()), x), 
                plans,
            ),
            key=lambda y: y[0],
        )[0]
        if closest_wday[0] < network.max_plan_diff_in_seconds:
            return closest_wday[1]
    
    def _extend_worker_days_to_create(to_create, plans):
        to_create.extend(
            [
                WorkerDay(
                    shop=approved_wd.shop,
                    employee_id=approved_wd.employee_id,
                    employment=approved_wd.employment,
                    work_hours=approved_wd.work_hours,
                    dttm_work_start=approved_wd.dttm_work_start,
                    dttm_work_end=approved_wd.dttm_work_end,
                    dt=approved_wd.dt,
                    is_fact=True,
                    is_approved=approved,
                    type=approved_wd.type,
                    created_by=last_edited_by,
                    last_edited_by=last_edited_by,
                    is_vacancy=approved_wd.is_vacancy,
                    is_outsource=approved_wd.is_outsource,
                    need_count_wh=True,
                    closest_plan_approved_id=approved_wd.id,
                    source=WorkerDay.SOURCE_FAST_EDITOR,
                )
                for approved_wd in plans
                for approved in [False, True]
            ]
        )

    wdays = WorkerDay.objects.filter(extra_q, **kwargs).filter(
        shop__network=network,
    ).select_related('type', 'shop', 'employment', 'closest_plan_approved').prefetch_related(
        models.Prefetch('worker_day_details', to_attr='details'),
    )

    groupped = {}
    details = {}
    for wd in wdays:
        if not wd.is_fact and not wd.is_approved:
            continue
        key = 'fact' if wd.is_fact else 'plan'
        groupped.setdefault(wd.employee_id, {}).setdefault(wd.dt, {}).setdefault(key, []).append(wd)
        if not wd.is_fact and wd.is_approved:
            details[wd.id] = wd.details
    
    wdays_to_update = []
    wdays_to_create = []
    with transaction.atomic():
        for employee_id, wdays_data in groupped.items():
            for dt, wdays in wdays_data.items():
                if not 'plan' in wdays:
                    continue
                if not 'fact' in wdays and create_fact:
                    _extend_worker_days_to_create(wdays_to_create, wdays['plan'])
                    continue
                for fact in wdays['fact']:
                    start_change_cond = (
                        not fact.dttm_work_start or 
                        (fact.created_by_id and override_manual_changes_start) or
                        (not fact.created_by_id and override_auto_start)
                    ) and set_start
                    end_change_cond = (
                        not fact.dttm_work_end or 
                        (fact.created_by_id and override_manual_changes_end) or
                        (not fact.created_by_id and override_auto_end)
                    ) and set_end
                    if start_change_cond:
                        fact.closest_plan_approved = _get_closest_plan(fact, wdays['plan'])
                        if fact.closest_plan_approved:
                            fact.dttm_work_start = fact.closest_plan_approved.dttm_work_start
                            fact.last_edited_by = last_edited_by
                    if end_change_cond:
                        fact.closest_plan_approved = _get_closest_plan(fact, wdays['plan'])
                        if fact.closest_plan_approved:
                            fact.dttm_work_end = fact.closest_plan_approved.dttm_work_end
                            fact.last_edited_by = last_edited_by
                    wdays_to_update.append(fact)
                if len(wdays['plan']) > len(list(filter(lambda x: x.is_approved, wdays['fact']))) and create_fact:
                    copied_plans_ids = list(map(lambda x: x.closest_plan_approved_id, wdays['fact']))
                    not_copied_plans = filter(lambda x: not x.id in copied_plans_ids, wdays['plan'])
                    _extend_worker_days_to_create(wdays_to_create, not_copied_plans)
                
        created_wdays = WorkerDay.objects.bulk_create(wdays_to_create)
        WorkerDayCashboxDetails.objects.bulk_create(
            [
                WorkerDayCashboxDetails(
                    work_type_id=detail.work_type_id,
                    worker_day=wd,
                    work_part=detail.work_part,
                )
                for wd in created_wdays
                for detail in details[wd.closest_plan_approved_id]
            ]
        )
        WorkerDay.objects.bulk_update(wdays_to_update, fields=['dttm_work_start', 'dttm_work_end', 'closest_plan_approved', 'last_edited_by'])

        recalc_work_hours.delay(id__in=list(map(lambda x: x.id, created_wdays)) + list(map(lambda x: x.id, wdays_to_update)))
