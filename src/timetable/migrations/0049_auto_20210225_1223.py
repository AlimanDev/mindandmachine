# Generated by Django 2.2.16 on 2021-02-25 12:23

from django.db import migrations


def create_or_replace_plan_and_fact_hours(apps, schema_editor):
    schema_editor.execute("""\
        create or replace view plan_and_fact_hours as
        select tt_pf.dt AS "Дата",
               tt_pf.shop_id AS "ID Магазина",
               tt_pf.shop_name AS "Магазин",
               tt_pf.shop_code AS "Код магазина",
               tt_pf.worker_id AS "ID Сотрудника",
               tt_pf.worker_fio AS "Сотрудник",
               tt_pf.fact_work_hours AS "Фактические часы работы",
               tt_pf.plan_work_hours AS "Плановые часы работы",
               tt_pf.late_arrival AS "Опоздания",
               tt_pf.early_departure AS "Ранний уход",
               tt_pf.is_vacancy::int as "Вакансия",
               tt_pf.is_vacancy as "is_vacancy",
               tt_pf.ticks_fact_count as "К-во отметок факт",
               tt_pf.ticks_plan_count as "К-во отметок план",
               tt_pf.worker_username as "Табельный номер",
               tt_pf.work_type_name as "Тип работ"
        from timetable_plan_and_fact_hours tt_pf
        where tt_pf.wd_type = 'W'""")


def create_or_replace_timetable_plan_and_fact_hours(apps, schema_editor):
    schema_editor.execute(
        """
        create or replace view timetable_plan_and_fact_hours as
        select string_agg(wd.id::text, '-'::text order by wd.is_fact) as id,
               wd.dt AS dt,
               wd.shop_id AS shop_id,
               s.name AS shop_name,
               s.code AS shop_code,
               wd.worker_id AS worker_id,
               wd.type as wd_type,
               concat(u.last_name, ' ', u.first_name, ' ', u.middle_name) AS worker_fio,
               coalesce(round((sum(date_part('epoch'::text, GREATEST(wd.work_hours, '00:00:00'::interval)) / 3600::double precision) FILTER (WHERE wd.is_fact is True))::numeric, 2), 0::double precision) AS fact_work_hours,
               coalesce(round((sum(date_part('epoch'::text, GREATEST(wd.work_hours, '00:00:00'::interval)) / 3600::double precision) FILTER (WHERE wd.is_fact is False))::numeric, 2), 0::double precision) AS plan_work_hours,
               (min(dttm_work_start) filter (where wd.is_fact is True) > min(dttm_work_start) filter (where wd.is_fact is False))::int AS late_arrival,
               (max(dttm_work_end) filter (where wd.is_fact is True) < max(dttm_work_end) filter (where wd.is_fact is False))::int AS early_departure,
               CASE WHEN (count(*) FILTER (WHERE wd.is_fact is False and wd.is_vacancy is True)) = 1 THEN True ELSE False END as is_vacancy,
               (count(*) FILTER (WHERE wd.is_fact is True and wd.dttm_work_start is not null) + count(*) FILTER (WHERE wd.is_fact is True and wd.dttm_work_end is not null))::int as ticks_fact_count,
               (coalesce(count(*) FILTER (WHERE wd.is_fact is False and wd.type='W'), 0) * 2)::int as ticks_plan_count,
               u.username as worker_username,
               coalesce(wd_details_wt_name.name, '') as work_type_name,
               DATE_TRUNC('minute', min(dttm_work_start) filter (where wd.is_fact is False)) AS dttm_work_start_plan,
               DATE_TRUNC('minute', max(dttm_work_end) filter (where wd.is_fact is False)) AS dttm_work_end_plan,
               DATE_TRUNC('minute', min(dttm_work_start) filter (where wd.is_fact is True)) AS dttm_work_start_fact,
               DATE_TRUNC('minute', max(dttm_work_end) filter (where wd.is_fact is True)) AS dttm_work_end_fact
        from timetable_workerday wd
                 inner join base_shop s on wd.shop_id = s.id
                 inner join base_user u on wd.worker_id = u.id
                 left join timetable_workerdaycashboxdetails wd_details on wd.id = wd_details.worker_day_id
                 left join timetable_worktype wd_details_wt on wd_details.work_type_id = wd_details_wt.id
                 left join timetable_worktypename wd_details_wt_name on wd_details_wt.work_type_name_id = wd_details_wt_name.id
        where wd.is_approved is True
            and NOT (wd.employment_id IS NULL AND wd.type = 'W' AND wd.worker_id IS NOT NULL)
            and wd.worker_id in (
                select be.user_id from base_employment be
                where be.user_id = wd.worker_id and 
                    (be.dt_hired <= wd.dt or be.dt_hired is null) and
                    (be.dt_fired >= wd.dt or be.dt_fired is null)
                )
        group by wd.dt,
                 wd.worker_id,
                 wd.type,
                 u.username,
                 concat(u.last_name, ' ', u.first_name, ' ', u.middle_name),
                 wd.shop_id,
                 s.name,
                 s.code,
                 coalesce(wd_details_wt_name.name, '')
        ;
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ('timetable', '0048_auto_20210217_1454'),
    ]

    operations = [
        migrations.RunPython(create_or_replace_plan_and_fact_hours, migrations.RunPython.noop),
        migrations.RunPython(create_or_replace_timetable_plan_and_fact_hours, migrations.RunPython.noop),
    ]