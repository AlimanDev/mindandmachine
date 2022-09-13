# Создано вручную 2022-08-29 13:01
# Миграция дропает и создаёт заново все views, зависящие от timetable_plan_and_fact_hours:
# metabase_financial_stat;
# performance;
# v_efficiency;
# plan_and_fact_hours;
# v_plan_and_fact_hours_1y;
# v_plan_and_fact_hours_2y;
# pobeda_performance;

from django.db import migrations

def update_views(apps, schema_editor):
    schema_editor.execute("""
    DROP VIEW IF EXISTS timetable_plan_and_fact_hours CASCADE;
    """)
    schema_editor.execute("""
    CREATE VIEW timetable_plan_and_fact_hours AS
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
    COALESCE(sum(date_part('epoch'::text, GREATEST(wd.work_hours, '00:00:00'::interval)) / 3600::double precision) FILTER (WHERE wd.is_fact IS TRUE AND (wd.created_by_id IS NOT NULL OR wd.last_edited_by_id IS NOT NULL)), 0::double precision) AS fact_manual_work_hours,
    sum(COALESCE(GREATEST(date_part('epoch'::text, wd_fact.dttm_work_start - (wd.dttm_work_start + shop_network.allowed_interval_for_late_arrival)) / 3600::double precision, 0::double precision), 0::double precision)) AS late_arrival_hours,
    sum(COALESCE(GREATEST(date_part('epoch'::text, wd.dttm_work_end - shop_network.allowed_interval_for_early_departure - wd_fact.dttm_work_end) / 3600::double precision, 0::double precision), 0::double precision)) AS early_departure_hours,
    count(*) FILTER (WHERE COALESCE(GREATEST(date_part('epoch'::text, wd_fact.dttm_work_start - (wd.dttm_work_start + shop_network.allowed_interval_for_late_arrival)) / 3600::double precision, 0::double precision), 0::double precision) > 0::double precision) AS late_arrival_count,
    count(*) FILTER (WHERE COALESCE(GREATEST(date_part('epoch'::text, wd.dttm_work_end - shop_network.allowed_interval_for_early_departure - wd_fact.dttm_work_end) / 3600::double precision, 0::double precision), 0::double precision) > 0::double precision) AS early_departure_count,
    sum(COALESCE(GREATEST(date_part('epoch'::text, wd.dttm_work_start - shop_network.allowed_interval_for_early_arrival - wd_fact.dttm_work_start) / 3600::double precision, 0::double precision), 0::double precision)) AS early_arrival_hours,
    sum(COALESCE(GREATEST(date_part('epoch'::text, wd_fact.dttm_work_end - (wd.dttm_work_end + shop_network.allowed_interval_for_late_departure)) / 3600::double precision, 0::double precision), 0::double precision)) AS late_departure_hours,
    count(*) FILTER (WHERE COALESCE(GREATEST(date_part('epoch'::text, wd.dttm_work_start - shop_network.allowed_interval_for_early_arrival - wd_fact.dttm_work_start) / 3600::double precision, 0::double precision), 0::double precision) > 0::double precision) AS early_arrival_count,
    count(*) FILTER (WHERE COALESCE(GREATEST(date_part('epoch'::text, wd_fact.dttm_work_end - (wd.dttm_work_end + shop_network.allowed_interval_for_late_departure)) / 3600::double precision, 0::double precision), 0::double precision) > 0::double precision) AS late_departure_count,
    COALESCE(sum(date_part('epoch'::text, GREATEST(wd.work_hours, '00:00:00'::interval)) / 3600::double precision) FILTER (WHERE wd.closest_plan_approved_id IS NULL AND wd.is_fact IS TRUE), 0::double precision) AS fact_without_plan_work_hours,
    count(*) FILTER (WHERE wd.closest_plan_approved_id IS NULL AND wd.is_fact IS TRUE) AS fact_without_plan_count,
    COALESCE(sum(COALESCE(GREATEST(date_part('epoch'::text, wd.work_hours - COALESCE(wd_fact.work_hours, '00:00:00'::interval)) / 3600::double precision, 0::double precision), 0::double precision)) FILTER (WHERE wd.is_fact IS FALSE), 0::double precision) AS lost_work_hours,
    count(*) FILTER (WHERE COALESCE(GREATEST(date_part('epoch'::text, wd.work_hours - COALESCE(wd_fact.work_hours, '00:00:00'::interval)) / 3600::double precision, 0::double precision), 0::double precision) > 0::double precision AND wd.is_fact IS FALSE) AS lost_work_hours_count,
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
     LEFT JOIN timetable_workerday wd_fact ON wd_fact.closest_plan_approved_id = wd.id AND wd_fact.is_approved IS TRUE
  WHERE wd.is_approved IS TRUE AND NOT (wd.employment_id IS NULL AND wd.type_id::text = 'W'::text AND wd.employee_id IS NOT NULL) AND (wd.employee_id IN ( SELECT be.employee_id
           FROM base_employment be
          WHERE be.employee_id = wd.employee_id AND (be.dt_hired <= wd.dt OR be.dt_hired IS NULL) AND (be.dt_fired >= wd.dt OR be.dt_fired IS NULL)))
  GROUP BY wd.dt, employee.user_id, employee.tabel_code, wd.type_id, u.username, (concat(u.last_name, ' ', u.first_name, ' ', u.middle_name)), wd.shop_id, s.name, s.code, (COALESCE(wd_details_wt_name.name, ''::character varying)), wd.employee_id, shop_network.id, user_network.id;
""")
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
    tt_pf.late_arrival_count AS "Опоздания",
    tt_pf.early_departure_count AS "Ранний уход",
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
  WHERE tt_pf.wd_type_id::text = 'W'::text AND tt_pf.dt > (CURRENT_DATE - '1 year'::interval)
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
    schema_editor.execute("""
    CREATE VIEW v_plan_and_fact_hours_1y AS
 SELECT tt_pf.dt AS "Дата",
    tt_pf.shop_id AS "ID Магазина",
    tt_pf.shop_name AS "Магазин",
    tt_pf.shop_code AS "Код магазина",
    tt_pf.employee_id::bigint AS "ID Сотрудника",
    tt_pf.worker_fio AS "Сотрудник",
    round(tt_pf.fact_work_hours::numeric, 2)::double precision AS "Фактические часы работы",
    round(tt_pf.plan_work_hours::numeric, 2)::double precision AS "Плановые часы работы",
    tt_pf.late_arrival_count AS "Опоздания",
    tt_pf.early_departure_count AS "Ранний уход",
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
  WHERE tt_pf.wd_type_id::text = 'W'::text AND tt_pf.dt > (CURRENT_DATE - '1 year'::interval)
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
  WHERE pc.dt >= (CURRENT_DATE - '1 year'::interval) AND pc.dt < (now() + '2 mons'::interval);
    """)
    schema_editor.execute("""
    CREATE VIEW plan_and_fact_hours AS
 SELECT tt_pf.dt AS "Дата",
    tt_pf.shop_id AS "ID Магазина",
    tt_pf.shop_name AS "Магазин",
    tt_pf.shop_code AS "Код магазина",
    tt_pf.employee_id::bigint AS "ID Сотрудника",
    tt_pf.worker_fio AS "Сотрудник",
    round(tt_pf.fact_work_hours::numeric, 2)::double precision AS "Фактические часы работы",
    round(tt_pf.plan_work_hours::numeric, 2)::double precision AS "Плановые часы работы",
    tt_pf.late_arrival_count AS "Опоздания",
    tt_pf.early_departure_count AS "Ранний уход",
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
    schema_editor.execute("""
    CREATE VIEW v_efficiency AS
 SELECT t.shop_id,
    t.income,
    t.dt,
    t.shop_code,
    t.income_name,
    t.income_code,
    ( SELECT sum(pc2.value) AS sum
           FROM forecast_periodclients pc2
             JOIN forecast_operationtype ot2 ON pc2.operation_type_id = ot2.id
             JOIN forecast_operationtypename otn2 ON ot2.operation_type_name_id = otn2.id
          WHERE ot2.shop_id = t.shop_id AND pc2.dttm_forecast::date = t.dt AND pc2.type::text = 'F'::text AND otn2.code::text = 'clients'::text AND pc2.dttm_forecast > (CURRENT_DATE - '1 year'::interval)) AS clients,
        CASE
            WHEN t.income_code::text = 'income'::text THEN ( SELECT sum(pf1."Фактические часы работы") AS sum
               FROM plan_and_fact_hours pf1
              WHERE pf1."ID Магазина" = t.shop_id AND pf1."Дата" = t.dt)
            WHEN t.income_code::text = 'income_seller'::text THEN ( SELECT sum(pf2."Фактические часы работы") AS sum
               FROM plan_and_fact_hours pf2
              WHERE pf2."ID Магазина" = t.shop_id AND pf2."Дата" = t.dt AND pf2."Тип работ"::text = 'Продавец-кассир'::text)
            WHEN t.income_code::text = 'income_mk'::text THEN ( SELECT sum(pf3."Фактические часы работы") AS sum
               FROM plan_and_fact_hours pf3
              WHERE pf3."ID Магазина" = t.shop_id AND pf3."Дата" = t.dt AND pf3."Тип работ"::text = 'Врач'::text)
            ELSE NULL::double precision
        END AS work_hours
   FROM ( SELECT s.id AS shop_id,
            sum(pc.value) AS income,
            pc.dttm_forecast::date AS dt,
            s.code AS shop_code,
            otn.name AS income_name,
            otn.code AS income_code
           FROM forecast_periodclients pc
             JOIN forecast_operationtype ot ON pc.operation_type_id = ot.id
             JOIN forecast_operationtypename otn ON ot.operation_type_name_id = otn.id
             JOIN base_shop s ON ot.shop_id = s.id
          WHERE pc.type::text = 'F'::text AND otn.code::text ~~ 'income%%'::text AND pc.dttm_forecast > (CURRENT_DATE - '1 year'::interval)
          GROUP BY s.id, s.code, (pc.dttm_forecast::date), otn.name, otn.code) t;
    """)
    schema_editor.execute("""
    CREATE VIEW performance AS
 SELECT pf."Дата" AS dt,
    ( SELECT sum(pc.value) AS sum
           FROM forecast_periodclients pc
             JOIN forecast_operationtype ot ON pc.operation_type_id = ot.id
             JOIN forecast_operationtypename otn ON ot.operation_type_name_id = otn.id
             JOIN base_shop s ON ot.shop_id = s.id
          WHERE ot.shop_id = pf."ID Магазина" AND pc.type::text = 'F'::text AND otn.code::text = 'income'::text AND pc.dttm_forecast::date = pf."Дата") AS income,
    sum(pf."Фактические часы работы") AS work_hours,
    pf."ID Магазина" AS shop_id,
    pf."Код магазина" AS shop_code
   FROM plan_and_fact_hours pf
  GROUP BY pf."Дата", pf."ID Магазина", pf."Код магазина";
    """)
    schema_editor.execute("""
    CREATE VIEW metabase_financial_stat AS
SELECT turnover.dt,
    turnover.shop_id,
    turnover.plan,
    turnover.fact,
    sum(fot."Плановые часы работы") AS fot_plan,
    sum(fot."Фактические часы работы") AS fot_fact,
    turnover.plan / NULLIF(sum(fot."Плановые часы работы"), 0::double precision) AS productivity_plan,
    turnover.fact / NULLIF(sum(fot."Фактические часы работы"), 0::double precision) AS productivity_fact,
    count(e.id) AS workers
   FROM metabase_to turnover
     LEFT JOIN plan_and_fact_hours fot ON turnover.shop_id = fot."ID Магазина" AND turnover.dt = fot."Дата"
     LEFT JOIN base_employment e ON e.shop_id = turnover.shop_id AND e.dt_hired <= turnover.dt AND (e.dt_fired IS NULL OR e.dt_fired >= turnover.dt)
  GROUP BY turnover.dt, turnover.shop_id, turnover.plan, turnover.fact;
    """)
    schema_editor.execute("""
    CREATE VIEW pobeda_performance AS
SELECT pf."Дата" AS dt,
   ( SELECT sum(pc.value) AS sum
         FROM forecast_periodclients pc
            JOIN forecast_operationtype ot ON pc.operation_type_id = ot.id
            JOIN forecast_operationtypename otn ON ot.operation_type_name_id = otn.id
            JOIN base_shop s ON ot.shop_id = s.id
         WHERE ot.shop_id = pf."ID Магазина" AND pc.type::text = 'F'::text AND otn.code::text = 'income'::text AND pc.dttm_forecast::date = pf."Дата") AS income,
   sum(pf."Фактические часы работы") AS work_hours,
   pf."ID Магазина" AS shop_id,
   pf."Код магазина" AS shop_code,
   ( SELECT sum(pc.value) AS sum
         FROM forecast_periodclients pc
            JOIN forecast_operationtype ot ON pc.operation_type_id = ot.id
            JOIN forecast_operationtypename otn ON ot.operation_type_name_id = otn.id
            JOIN base_shop s ON ot.shop_id = s.id
         WHERE ot.shop_id = pf."ID Магазина" AND pc.type::text = 'F'::text AND otn.code::text = 'goods_count'::text AND pc.dttm_forecast::date = pf."Дата") AS goods_count
FROM plan_and_fact_hours pf
GROUP BY pf."Дата", pf."ID Магазина", pf."Код магазина";
    """)

class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0118_RND-340'),
    ]

    operations = [
        migrations.RunPython(update_views, migrations.RunPython.noop),
    ]
