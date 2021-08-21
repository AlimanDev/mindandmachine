# Generated by Django 2.2.16 on 2021-08-18 20:24
import django.db.models.deletion
from django.db import migrations, models

TYPE_HOLIDAY = 'H'
TYPE_WORKDAY = 'W'
TYPE_VACATION = 'V'
TYPE_SICK = 'S'
TYPE_QUALIFICATION = 'Q'
TYPE_ABSENSE = 'A'
TYPE_MATERNITY = 'M'
TYPE_BUSINESS_TRIP = 'T'
TYPE_ETC = 'O'
TYPE_EMPTY = 'E'
TYPE_SELF_VACATION = 'TV'  # TV, а не SV, потому что так уже написали в документации клиенту


def create_worker_day_types(apps, schema_editor):
    WorkerDayType = apps.get_model('timetable', 'WorkerDayType')

    wd_types_to_create = [
        WorkerDayType(
            code=TYPE_WORKDAY,
            name='Рабочий день',
            short_name='Р/Д',
            html_color='#f7f7f7',
            use_in_plan=True,
            use_in_fact=True,
            excel_load_code='Я',
            is_dayoff=False,
            is_work_hours=True,
            is_reduce_norm=False,
            is_system=True,
            show_stat_in_days=False,
            show_stat_in_hours=False,
            ordering=100,
        ),
        WorkerDayType(
            code=TYPE_HOLIDAY,
            name='Выходной',
            short_name='ВЫХ',
            html_color='#7ae7a5',
            use_in_plan=True,
            use_in_fact=False,
            excel_load_code='В',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=True,
            show_stat_in_hours=False,
            ordering=95,
        ),
        WorkerDayType(
            code=TYPE_VACATION,
            name='Отпуск',
            short_name='ОТП',
            html_color='#e6e588',
            use_in_plan=True,
            use_in_fact=False,
            excel_load_code='ОТ',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=True,
            is_system=False,
            show_stat_in_days=True,
            show_stat_in_hours=False,
            ordering=90,
        ),
        WorkerDayType(
            code=TYPE_SELF_VACATION,
            name='Отпуск за свой счет',
            short_name='ОЗСС',
            html_color='#a3a34b',
            use_in_plan=True,
            use_in_fact=False,
            excel_load_code='ДО',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=True,
            is_system=False,
            show_stat_in_days=True,
            show_stat_in_hours=False,
            ordering=85,
        ),
        WorkerDayType(
            code=TYPE_QUALIFICATION,
            name='Учёба',
            short_name='УЧ',
            html_color='#2036c0',
            use_in_plan=True,
            use_in_fact=True,
            excel_load_code='У',
            is_dayoff=False,
            is_work_hours=True,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=True,
            show_stat_in_hours=False,
            ordering=80,
        ),
        WorkerDayType(
            code=TYPE_SICK,
            name='Больничный',
            short_name='БОЛ',
            html_color='#c13329',
            use_in_plan=True,
            use_in_fact=False,
            excel_load_code='Б',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=True,
            is_system=False,
            show_stat_in_days=True,
            show_stat_in_hours=False,
            ordering=75,
        ),
        WorkerDayType(
            code=TYPE_ABSENSE,
            name='Неявка',
            short_name='ОТС',
            html_color='#c16627',
            use_in_plan=True,
            use_in_fact=False,
            excel_load_code='НН',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=False,
            show_stat_in_hours=False,
            ordering=70,
        ),
        WorkerDayType(
            code=TYPE_MATERNITY,
            name='Декрет',
            short_name='ДЕК',
            html_color='#b742a5',
            use_in_plan=True,
            use_in_fact=False,
            excel_load_code='ОЖ',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=True,
            is_system=False,
            show_stat_in_days=False,
            show_stat_in_hours=False,
            ordering=65,
        ),
        WorkerDayType(
            code=TYPE_BUSINESS_TRIP,
            name='Командировка',
            short_name='КОМ',
            html_color='#6a8acc',
            use_in_plan=True,
            use_in_fact=True,
            excel_load_code='К',
            is_dayoff=False,
            is_work_hours=True,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=False,
            show_stat_in_hours=False,
            ordering=60,
        ),
        WorkerDayType(
            code=TYPE_ETC,
            name='Другое',
            short_name='ДР',
            html_color='#a28ba6',
            use_in_plan=True,
            use_in_fact=False,
            excel_load_code='ДР',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=False,
            show_stat_in_hours=False,
            ordering=55,
        ),
        WorkerDayType(
            code=TYPE_EMPTY,
            name='Удаление',
            short_name='УД',
            html_color='#ffffff',
            use_in_plan=False,
            use_in_fact=True,
            excel_load_code='УД',
            is_dayoff=True,
            is_work_hours=False,
            is_reduce_norm=False,
            is_system=False,
            show_stat_in_days=False,
            show_stat_in_hours=False,
            ordering=50,
        ),
    ]

    WorkerDayType.objects.bulk_create(wd_types_to_create)


def drop_views(apps, schema_editor):
    schema_editor.execute(
        "drop view performance; drop view v_mda_users; drop view metabase_financial_stat; drop view plan_and_fact_hours; drop view timetable_plan_and_fact_hours; ")


def recreate_views(apps, schema_editor):
    schema_editor.execute("""CREATE OR REPLACE VIEW performance AS
 SELECT t.dt,
    t.income,
    COALESCE(( SELECT date_part('epoch'::text, sum(GREATEST(wd.work_hours, '00:00:00'::interval))) / 3600::double precision
           FROM timetable_workerday wd
          WHERE wd.dt = t.dt AND wd.shop_id = t.shop_id AND wd.is_approved = true AND wd.is_fact = true AND NOT (wd.employment_id IS NULL AND wd.type_id::text = 'W'::text AND wd.employee_id IS NOT NULL)), 0::double precision) AS work_hours,
    t.shop_id,
    t.shop_code
   FROM ( SELECT s.id AS shop_id,
            s.code AS shop_code,
            pc.dttm_forecast::date AS dt,
            sum(pc.value) AS income
           FROM forecast_periodclients pc
             JOIN forecast_operationtype ot ON pc.operation_type_id = ot.id
             JOIN forecast_operationtypename otn ON ot.operation_type_name_id = otn.id
             JOIN base_shop s ON ot.shop_id = s.id
          WHERE pc.type::text = 'F'::text AND otn.code::text = 'income'::text
          GROUP BY s.id, s.code, (pc.dttm_forecast::date)) t;""")

    schema_editor.execute("""\
CREATE OR REPLACE VIEW v_mda_users AS
  SELECT DISTINCT u.id,
    u.username,
    u.last_name,
    u.first_name,
    u.middle_name,
    u.email,
    e.dt_hired,
    e.dt_fired,
    e.dttm_deleted IS NULL AND e.dt_hired <= CURRENT_TIMESTAMP::date AND (e.dt_fired IS NULL OR e.dt_fired >= CURRENT_TIMESTAMP::date) AS active,
        CASE
            WHEN s.level = 0 THEN 'COMPANY'::text
            WHEN s.level = 1 THEN 'DIVISION'::text
            WHEN s.level = 2 THEN 'REGION'::text
            WHEN s.level = 3 THEN 'SHOP'::text
            ELSE NULL::text
        END AS level,
        CASE
            WHEN e.dttm_deleted IS NULL AND e.dt_hired <= CURRENT_TIMESTAMP::date AND (e.dt_fired IS NULL OR e.dt_fired >= CURRENT_TIMESTAMP::date) AND e.id = (( SELECT e2.id
               FROM base_employment e2
                 JOIN base_employee employee2 ON e2.employee_id = employee2.id
                 JOIN base_user u2 ON employee2.user_id = u2.id
                 JOIN base_shop s2 ON e2.shop_id = s2.id
                 LEFT JOIN base_workerposition wp2 ON e2.position_id = wp2.id
                 LEFT JOIN base_group fg2 ON e2.function_group_id = fg2.id
                 LEFT JOIN base_group g2 ON wp2.group_id = g2.id
              WHERE s2.id = s.id AND (g2.code::text = 'director'::text OR fg2.code::text = 'director'::text) AND e2.dttm_deleted IS NULL AND e2.dt_hired <= CURRENT_TIMESTAMP::date AND (e2.dt_fired IS NULL OR e2.dt_fired >= CURRENT_TIMESTAMP::date)
              ORDER BY ((EXISTS ( SELECT wd2.id
                       FROM timetable_workerday wd2
                      WHERE wd2.employee_id = employee2.id AND wd2.dt = now()::date AND (wd2.type_id::text = ANY (ARRAY['M'::character varying, 'S'::character varying, 'V'::character varying]::text[])) AND wd2.is_fact IS FALSE AND wd2.is_approved IS TRUE))), e2.is_visible DESC, e2.norm_work_hours DESC, ((EXISTS ( SELECT ds.id
                       FROM base_shop ds
                      WHERE ds.director_id = employee2.user_id))) DESC, e2.dt_hired DESC
             LIMIT 1)) THEN 'DIR'::text
            WHEN NOT (e.dttm_deleted IS NULL AND e.dt_hired <= CURRENT_TIMESTAMP::date AND (e.dt_fired IS NULL OR e.dt_fired >= CURRENT_TIMESTAMP::date)) AND (g.code::text = 'director'::text OR fg.code::text = 'director'::text) THEN 'DIR'::text
            ELSE 'MANAGER'::text
        END AS role,
    s.name AS shop_name,
    s.code AS shop_code,
    wp.name AS position_name,
    wp.code AS position_code,
    g.name AS position_group_name,
    g.code AS position_group_code,
    fg.name AS func_group_name,
    fg.code AS func_group_code,
    u.dttm_modified AS user_last_modified,
    e.dttm_modified AS employment_last_modified,
    wp.dttm_modified AS position_last_modified,
    GREATEST(u.dttm_modified, e.dttm_modified, wp.dttm_modified) AS last_modified,
    e.code
   FROM base_employment e
     JOIN base_employee employee ON e.employee_id = employee.id
     JOIN base_user u ON employee.user_id = u.id
     JOIN base_shop s ON e.shop_id = s.id
     LEFT JOIN base_workerposition wp ON e.position_id = wp.id
     LEFT JOIN base_group fg ON e.function_group_id = fg.id
     LEFT JOIN base_group g ON wp.group_id = g.id
     LEFT JOIN timetable_workerday wdpa ON employee.id = wdpa.employee_id AND wdpa.dt = now()::date AND wdpa.is_fact = false AND wdpa.is_approved = true
  WHERE true AND e.dttm_deleted IS NULL AND (s.dttm_deleted IS NULL OR s.dttm_deleted >= (CURRENT_TIMESTAMP - '60 days'::interval)) AND (s.dt_closed IS NULL OR s.dt_closed >= (CURRENT_TIMESTAMP - '60 days'::interval)) AND (e.dt_fired > '2020-10-01'::date AND e.dt_hired < e.dt_fired OR e.dt_fired IS NULL) AND e.dt_hired <= CURRENT_TIMESTAMP::date AND (NOT g.code::text = 'director'::text OR wp.group_id IS NULL OR g.code::text = 'director'::text AND (wdpa.type_id IS NULL OR (wdpa.type_id::text <> ALL (ARRAY['M'::text])))) AND s.level = 3;""")

    schema_editor.execute("""\
CREATE OR REPLACE VIEW timetable_plan_and_fact_hours AS
 SELECT string_agg(wd.id::text, '-'::text ORDER BY wd.is_fact) AS id,
    wd.dt,
    wd.shop_id,
    s.name AS shop_name,
    s.code AS shop_code,
    employee.user_id AS worker_id,
    wd.type_id AS wd_type_id,
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
    (COALESCE(count(*) FILTER (WHERE wd.is_fact IS FALSE AND wd.type_id::text = 'W'::text), 0::bigint) * 2)::integer AS ticks_plan_count,
    u.username AS worker_username,
    COALESCE(wd_details_wt_name.name, ''::character varying) AS work_type_name,
    date_trunc('minute'::text, min(wd.dttm_work_start) FILTER (WHERE wd.is_fact IS FALSE)) AS dttm_work_start_plan,
    date_trunc('minute'::text, max(wd.dttm_work_end) FILTER (WHERE wd.is_fact IS FALSE)) AS dttm_work_end_plan,
    date_trunc('minute'::text, min(wd.dttm_work_start) FILTER (WHERE wd.is_fact IS TRUE)) AS dttm_work_start_fact,
    date_trunc('minute'::text, max(wd.dttm_work_end) FILTER (WHERE wd.is_fact IS TRUE)) AS dttm_work_end_fact,
    count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.dttm_work_start IS NOT NULL)::integer AS ticks_comming_fact_count,
    count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.dttm_work_end IS NOT NULL)::integer AS ticks_leaving_fact_count,
    count(*) FILTER (WHERE wd.is_fact IS FALSE AND wd.created_by_id IS NULL AND wd.last_edited_by_id IS NULL AND wd.work_hours IS NOT NULL AND wd.work_hours > '00:00:00'::interval) AS auto_created_plan,
    count(*) FILTER (WHERE wd.is_fact IS TRUE AND wd.created_by_id IS NULL AND wd.last_edited_by_id IS NULL AND wd.work_hours IS NOT NULL AND wd.work_hours > '00:00:00'::interval) AS auto_created_fact,
    employee.tabel_code,
    wd.employee_id,
    shop_network.name AS shop_network,
    user_network.name AS user_network,
    shop_network.id <> user_network.id AS is_outsource
   FROM timetable_workerday wd
     JOIN base_shop s ON wd.shop_id = s.id
     JOIN base_network shop_network ON shop_network.id = s.network_id
     JOIN base_employee employee ON wd.employee_id = employee.id
     JOIN base_user u ON employee.user_id = u.id
     JOIN base_network user_network ON user_network.id = u.network_id
     LEFT JOIN timetable_workerdaycashboxdetails wd_details ON wd.id = wd_details.worker_day_id AND wd_details.id = (( SELECT max(wd_details2.id) AS max
           FROM timetable_workerdaycashboxdetails wd_details2
          WHERE wd.id = wd_details2.worker_day_id))
     LEFT JOIN timetable_worktype wd_details_wt ON wd_details.work_type_id = wd_details_wt.id
     LEFT JOIN timetable_worktypename wd_details_wt_name ON wd_details_wt.work_type_name_id = wd_details_wt_name.id
  WHERE wd.is_approved IS TRUE AND NOT (wd.employment_id IS NULL AND wd.type_id::text = 'W'::text AND wd.employee_id IS NOT NULL) AND (wd.employee_id IN ( SELECT be.employee_id
           FROM base_employment be
          WHERE be.employee_id = wd.employee_id AND (be.dt_hired <= wd.dt OR be.dt_hired IS NULL) AND (be.dt_fired >= wd.dt OR be.dt_fired IS NULL)))
  GROUP BY wd.dt, employee.user_id, employee.tabel_code, wd.type_id, u.username, (concat(u.last_name, ' ', u.first_name, ' ', u.middle_name)), wd.shop_id, s.name, s.code, (COALESCE(wd_details_wt_name.name, ''::character varying)), wd.employee_id, shop_network.id, user_network.id;"""
                          )

    schema_editor.execute("""\
CREATE OR REPLACE VIEW plan_and_fact_hours AS
 SELECT tt_pf.dt AS "Дата",
    tt_pf.shop_id AS "ID Магазина",
    tt_pf.shop_name AS "Магазин",
    tt_pf.shop_code AS "Код магазина",
    tt_pf.employee_id::bigint AS "ID Сотрудника",
    tt_pf.worker_fio AS "Сотрудник",
    round(tt_pf.fact_work_hours::numeric, 2)::double precision AS "Фактические часы работы",
    round(tt_pf.plan_work_hours::numeric, 2)::double precision AS "Плановые часы работы",
    tt_pf.late_arrival AS "Опоздания",
    tt_pf.early_departure AS "Ранний уход",
    tt_pf.is_vacancy::integer AS "Вакансия",
    tt_pf.is_vacancy,
    tt_pf.ticks_fact_count AS "К-во отметок факт",
    tt_pf.ticks_plan_count AS "К-во отметок план",
    tt_pf.worker_username AS "Табельный номер",
    tt_pf.work_type_name AS "Тип работ",
    tt_pf.auto_created_plan AS "Авт-ки созданный план",
    tt_pf.auto_created_fact AS "Авт-ки созданный факт",
    tt_pf.tabel_code AS "Табельный номер трудоустройства",
    tt_pf.worker_id AS "ID Пользователя",
    tt_pf.shop_network AS "Сеть Подразделения",
    tt_pf.user_network AS "Сеть Сотрудника",
    tt_pf.is_outsource::integer AS "Аутсорс",
    NULL::double precision AS "Норма часов (для суммы)"
   FROM timetable_plan_and_fact_hours tt_pf
  WHERE tt_pf.wd_type_id::text = 'W'::text
UNION ALL
 SELECT pc.dt AS "Дата",
    pc.shop_id AS "ID Магазина",
    NULL::character varying(128) AS "Магазин",
    pc.code AS "Код магазина",
    pc.employee_id::bigint AS "ID Сотрудника",
    NULL::text AS "Сотрудник",
    NULL::double precision AS "Фактические часы работы",
    NULL::double precision AS "Плановые часы работы",
    NULL::integer AS "Опоздания",
    NULL::integer AS "Ранний уход",
    NULL::integer AS "Вакансия",
    NULL::boolean AS is_vacancy,
    NULL::integer AS "К-во отметок факт",
    NULL::integer AS "К-во отметок план",
    NULL::character varying(150) AS "Табельный номер",
    NULL::character varying AS "Тип работ",
    NULL::bigint AS "Авт-ки созданный план",
    NULL::bigint AS "Авт-ки созданный факт",
    NULL::character varying(64) AS "Табельный номер трудоустройства",
    pc.user_id AS "ID Пользователя",
    NULL::character varying(128) AS "Сеть Подразделения",
    NULL::character varying(128) AS "Сеть Сотрудника",
    NULL::integer AS "Аутсорс",
    ( SELECT sum(pc2.norm_hours) / COALESCE(NULLIF(count(pc2.id), 0), 1::bigint)::double precision
           FROM prod_cal pc2
          WHERE pc.employee_id = pc2.employee_id AND date_trunc('month'::text, pc.dt::timestamp with time zone) = date_trunc('month'::text, pc2.dt::timestamp with time zone)) AS "Норма часов (для суммы)"
   FROM prod_cal pc
  WHERE pc.dt >= '2020-01-01'::date AND pc.dt < (now() + '2 mons'::interval);
""")

    schema_editor.execute("""\
CREATE OR REPLACE VIEW metabase_financial_stat AS
SELECT turnover.dt,
    turnover.shop_id,
    turnover.plan,
    turnover.fact,
    sum(fot."Плановые часы работы") AS fot_plan,
    sum(fot."Фактические часы работы") AS fot_fact,
    (turnover.plan / NULLIF(sum(fot."Плановые часы работы"), (0)::double precision)) AS productivity_plan,
    (turnover.fact / NULLIF(sum(fot."Фактические часы работы"), (0)::double precision)) AS productivity_fact,
    count(e.id) AS workers
FROM ((public.metabase_to turnover
    LEFT JOIN public.plan_and_fact_hours fot ON (((turnover.shop_id = fot."ID Магазина") AND (turnover.dt = fot."Дата"))))
    LEFT JOIN public.base_employment e ON (((e.shop_id = turnover.shop_id) AND (e.dt_hired <= turnover.dt) AND ((e.dt_fired IS NULL) OR (e.dt_fired >= turnover.dt)))))
GROUP BY turnover.dt, turnover.shop_id, turnover.plan, turnover.fact;
""")


class Migration(migrations.Migration):
    dependencies = [
        ('timetable', '0082_auto_20210819_2214'),
    ]

    operations = [
        migrations.RunPython(create_worker_day_types, migrations.RunPython.noop),
        migrations.RunPython(drop_views, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='timesheet',
            name='fact_timesheet_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='fact_timesheet', to='timetable.WorkerDayType'),
        ),
        migrations.AlterField(
            model_name='timesheet',
            name='main_timesheet_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='main_timesheet', to='timetable.WorkerDayType'),
        ),
        migrations.AlterField(
            model_name='workerday',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkerDayType'),
        ),
        migrations.AlterField(
            model_name='workerdaypermission',
            name='wd_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkerDayType',
                                    verbose_name='Тип дня'),
        ),
        migrations.AlterField(
            model_name='planandfacthours',
            name='wd_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='timetable.WorkerDayType'),
        ),
        migrations.RunPython(recreate_views, migrations.RunPython.noop),
    ]
