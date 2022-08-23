# Создано вручную 2022-08-23 13:53

from django.db import migrations

def create_or_update_view_v_plan_and_fact_hours_2y(apps, schema_editor):
    schema_editor.execute("DROP VIEW IF EXISTS  v_plan_and_fact_hours_2y;")
    schema_editor.execute("""
    CREATE VIEW v_plan_and_fact_hours_2y AS
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
  WHERE tt_pf.wd_type::text = 'W'::text AND tt_pf.dt > (CURRENT_DATE - '1 year'::interval)
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
  WHERE pc.dt >= (CURRENT_DATE - '2 years'::interval) AND pc.dt < (now() + '2 mons'::interval);
    """)


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0117_auto_20220321_0923'),
    ]

    operations = [
        migrations.RunPython(create_or_update_view_v_plan_and_fact_hours_2y, migrations.RunPython.noop),
    ]
