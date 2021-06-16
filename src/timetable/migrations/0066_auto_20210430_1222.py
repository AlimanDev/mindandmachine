# Generated by Django 2.2.16 on 2021-04-30 12:22

import django.db.models.deletion
from django.db import migrations, models


def add_outsource_fields(apps, schema_editor):
    sql = """
        CREATE OR REPLACE VIEW timetable_plan_and_fact_hours AS
        SELECT string_agg(wd.id::text, '-'::text ORDER BY wd.is_fact) AS id,
        wd.dt,
        wd.shop_id,
        s.name AS shop_name,
        s.code AS shop_code,
        employee.user_id AS worker_id,
        wd.type AS wd_type,
        concat(u.last_name, ' ', u.first_name, ' ', u.middle_name) AS worker_fio,
        COALESCE(sum(date_part('epoch'::text, GREATEST(wd.work_hours, '00:00:00'::interval)) / 3600::double precision) FILTER (WHERE wd.is_fact IS TRUE), 0::double precision) AS fact_work_hours,
        COALESCE(sum(date_part('epoch'::text, GREATEST(wd.work_hours, '00:00:00'::interval)) / 3600::double precision) FILTER (WHERE wd.is_fact IS FALSE), 0::double precision) AS plan_work_hours,
        ((min(wd.dttm_work_start) FILTER (WHERE wd.is_fact IS TRUE) - min(wd.dttm_work_start) FILTER (WHERE wd.is_fact IS FALSE)) > shop_network.allowed_interval_for_late_arrival)::integer AS late_arrival,
        ((max(wd.dttm_work_end) FILTER (WHERE wd.is_fact IS FALSE) - max(wd.dttm_work_end) FILTER (WHERE wd.is_fact IS TRUE)) > shop_network.allowed_interval_for_early_departure)::integer AS early_departure,
            CASE
                WHEN count(*) FILTER (WHERE wd.is_fact IS FALSE AND wd.is_vacancy IS TRUE) = 1 THEN true
                ELSE false
            END AS is_vacancy,
        (count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.dttm_work_start IS NOT NULL) + count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.dttm_work_end IS NOT NULL))::integer AS ticks_fact_count,
        (COALESCE(count(*) FILTER (WHERE wd.is_fact IS FALSE AND wd.type::text = 'W'::text), 0::bigint) * 2)::integer AS ticks_plan_count,
        u.username AS worker_username,
        COALESCE(wd_details_wt_name.name, ''::character varying) AS work_type_name,
        date_trunc('minute'::text, min(wd.dttm_work_start) FILTER (WHERE wd.is_fact IS FALSE)) AS dttm_work_start_plan,
        date_trunc('minute'::text, max(wd.dttm_work_end) FILTER (WHERE wd.is_fact IS FALSE)) AS dttm_work_end_plan,
        date_trunc('minute'::text, min(wd.dttm_work_start) FILTER (WHERE wd.is_fact IS TRUE)) AS dttm_work_start_fact,
        date_trunc('minute'::text, max(wd.dttm_work_end) FILTER (WHERE wd.is_fact IS TRUE)) AS dttm_work_end_fact,
        count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.dttm_work_start IS NOT NULL)::integer AS ticks_comming_fact_count,
        count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.dttm_work_end IS NOT NULL)::integer AS ticks_leaving_fact_count,
        count(*) FILTER (WHERE wd.is_fact IS FALSE AND wd.created_by_id IS NULL AND wd.last_edited_by_id IS NULL AND wd.work_hours IS NOT NULL AND wd.work_hours > interval '0 second') AS auto_created_plan,
        count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.created_by_id IS NULL AND wd.last_edited_by_id IS NULL AND wd.work_hours IS NOT NULL AND wd.work_hours > interval '0 second') AS auto_created_fact,
           employee.tabel_code,
           wd.employee_id,
           shop_network.name as shop_network,
           user_network.name as user_network,
           (shop_network.id != user_network.id)::boolean as is_outsource
    from timetable_workerday wd
         INNER JOIN base_shop s on wd.shop_id = s.id
         INNER JOIN base_network shop_network on shop_network.id = s.network_id
         INNER JOIN base_employee employee on wd.employee_id = employee.id
         INNER JOIN base_user u on employee.user_id = u.id
         INNER JOIN base_network user_network on user_network.id = u.network_id
         LEFT JOIN timetable_workerdaycashboxdetails wd_details ON wd.id = wd_details.worker_day_id AND wd_details.id = (( SELECT max(wd_details2.id) AS max
           FROM timetable_workerdaycashboxdetails wd_details2
          WHERE wd.id = wd_details2.worker_day_id))
         LEFT JOIN timetable_worktype wd_details_wt ON wd_details.work_type_id = wd_details_wt.id
         LEFT JOIN timetable_worktypename wd_details_wt_name ON wd_details_wt.work_type_name_id = wd_details_wt_name.id
      WHERE wd.is_approved IS TRUE AND NOT (wd.employment_id IS NULL AND wd.type::text = 'W'::text AND wd.employee_id IS NOT NULL) AND (wd.employee_id IN ( SELECT be.employee_id
               FROM base_employment be
              WHERE be.employee_id = wd.employee_id AND (be.dt_hired <= wd.dt OR be.dt_hired IS NULL) AND (be.dt_fired >= wd.dt OR be.dt_fired IS NULL)))
      GROUP BY wd.dt,
               employee.user_id,
               employee.tabel_code,
               wd.type,
               u.username,
               (concat(u.last_name, ' ', u.first_name, ' ', u.middle_name)),
               wd.shop_id,
               s.name,
               s.code,
               (COALESCE(wd_details_wt_name.name, ''::character varying)),
               wd.employee_id,
               shop_network.id,
               user_network.id;"""
    schema_editor.execute(sql)

    schema_editor.execute("""\
            create or replace view plan_and_fact_hours as
            select tt_pf.dt AS "Дата",
                   tt_pf.shop_id AS "ID Магазина",
                   tt_pf.shop_name AS "Магазин",
                   tt_pf.shop_code AS "Код магазина",
                   tt_pf.employee_id::bigint AS "ID Сотрудника",
                   tt_pf.worker_fio AS "Сотрудник",
                   round(tt_pf.fact_work_hours::numeric, 2)::double precision AS "Фактические часы работы",
                   round(tt_pf.plan_work_hours::numeric, 2)::double precision AS "Плановые часы работы",
                   tt_pf.late_arrival AS "Опоздания",
                   tt_pf.early_departure AS "Ранний уход",
                   tt_pf.is_vacancy::int as "Вакансия",
                   tt_pf.is_vacancy as "is_vacancy",
                   tt_pf.ticks_fact_count as "К-во отметок факт",
                   tt_pf.ticks_plan_count as "К-во отметок план",
                   tt_pf.worker_username as "Табельный номер",
                   tt_pf.work_type_name as "Тип работ",
                   tt_pf.auto_created_plan as "Авт-ки созданный план",
                   tt_pf.auto_created_fact as "Авт-ки созданный факт",
                   tt_pf.tabel_code AS "Табельный номер трудоустройства",
                   tt_pf.worker_id AS "ID Пользователя",
                   tt_pf.shop_network AS "Сеть Подразделения",
                   tt_pf.user_network AS "Сеть Сотрудника",
                   tt_pf.is_outsource::int as "Аутсорс"
            from timetable_plan_and_fact_hours tt_pf
            where tt_pf.wd_type = 'W'""")


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0065_attendancerecords_employee'),
    ]

    operations = [
        migrations.RunPython(add_outsource_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='worktype',
            name='shop',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_types', to='base.Shop'),
        ),
        migrations.AlterField(
            model_name='worktype',
            name='work_type_name',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_types', to='timetable.WorkTypeName'),
        ),
    ]