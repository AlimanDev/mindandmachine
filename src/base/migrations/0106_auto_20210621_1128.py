# Generated by Django 2.2.16 on 2021-06-21 11:28

from django.db import migrations, models

def drop_views(apps, schema_editor):
    schema_editor.execute("drop view metabase_financial_stat; drop view plan_and_fact_hours; drop view prod_cal; drop view v_mda_users; drop view prod_cal_work_hours;")

def create_views(apps, schema_editor):
    schema_editor.execute(
        """
        CREATE OR REPLACE VIEW prod_cal AS
    SELECT pd.id,
        pd.dt,
        employee.user_id,
        employment.id AS employment_id,
        u.username,
        employment.shop_id,
        s.code,
        pd.region_id,
        sum(
            CASE
                WHEN pd.type::text = 'W'::text THEN 8::double precision * COALESCE(wp.hours_in_a_week::integer, 40)::double precision / 40::double precision * employment.norm_work_hours::double precision / 100::double precision
                WHEN pd.type::text = 'S'::text THEN 8::double precision * COALESCE(wp.hours_in_a_week::integer, 40)::double precision / 40::double precision * employment.norm_work_hours::double precision / 100::double precision - 1::double precision
                ELSE 0::double precision
            END) AS norm_hours,
        employment.employee_id
       FROM base_employment employment
         JOIN base_shop s ON employment.shop_id = s.id
         JOIN base_region r ON s.region_id = r.id
         JOIN base_productionday pd ON
             (pd.dt >= employment.dt_hired OR employment.dt_hired IS NULL)
             AND (pd.dt <= employment.dt_fired OR employment.dt_fired IS NULL)
             AND (pd.region_id = r.id or pd.region_id = r.parent_id)
                 AND pd.id = (
                     SELECT pd2.id FROM base_productionday pd2 WHERE
                         (pd2.dt >= employment.dt_hired OR employment.dt_hired IS NULL)
                         AND (pd2.dt <= employment.dt_fired OR employment.dt_fired IS NULL)
                         AND (pd2.region_id = r.id or pd2.region_id = r.parent_id)
                         AND pd2.dt = pd.dt
                     ORDER BY pd2.region_id = r.id DESC, pd2.region_id = r.parent_id DESC
                     LIMIT 1
                 )
         JOIN base_employee employee ON employment.employee_id = employee.id
         JOIN base_user u ON employee.user_id = u.id
         LEFT JOIN base_workerposition wp ON employment.position_id = wp.id AND pd.dt >= '2020-01-01'::date
      WHERE employment.dttm_deleted IS NULL
      GROUP BY pd.id, pd.dt, employee.user_id, employment.id, u.username, employment.shop_id, s.code, pd.region_id;
        """
    )
    schema_editor.execute("""\
        CREATE OR REPLACE VIEW plan_and_fact_hours as
        SELECT tt_pf.dt                                                   AS "Дата",
               tt_pf.shop_id                                              AS "ID Магазина",
               tt_pf.shop_name                                            AS "Магазин",
               tt_pf.shop_code                                            AS "Код магазина",
               tt_pf.employee_id::bigint                                  AS "ID Сотрудника",
               tt_pf.worker_fio                                           AS "Сотрудник",
               round(tt_pf.fact_work_hours::numeric, 2)::double precision AS "Фактические часы работы",
               round(tt_pf.plan_work_hours::numeric, 2)::double precision AS "Плановые часы работы",
               tt_pf.late_arrival                                         AS "Опоздания",
               tt_pf.early_departure                                      AS "Ранний уход",
               tt_pf.is_vacancy::integer                                  AS "Вакансия",
               tt_pf.is_vacancy,
               tt_pf.ticks_fact_count                                     AS "К-во отметок факт",
               tt_pf.ticks_plan_count                                     AS "К-во отметок план",
               tt_pf.worker_username                                      AS "Табельный номер",
               tt_pf.work_type_name                                       AS "Тип работ",
               tt_pf.auto_created_plan                                    AS "Авт-ки созданный план",
               tt_pf.auto_created_fact                                    AS "Авт-ки созданный факт",
               tt_pf.tabel_code                                           AS "Табельный номер трудоустройства",
               tt_pf.worker_id                                            AS "ID Пользователя",
               tt_pf.shop_network                                         AS "Сеть Подразделения",
               tt_pf.user_network                                         AS "Сеть Сотрудника",
               tt_pf.is_outsource::integer                                AS "Аутсорс",
               null                                                       as "Норма часов (для суммы)"
        from timetable_plan_and_fact_hours tt_pf
        where tt_pf.wd_type::text = 'W'::text
        UNION ALL
        SELECT pc.dt                                                                                 AS "Дата",
               pc.shop_id                                                                            AS "ID Магазина",
               null::character varying(128)                                                          AS "Магазин",
               pc.code                                                                               AS "Код магазина",
               pc.employee_id::bigint                                                                AS "ID Сотрудника",
               null                                                                                  AS "Сотрудник",
               null                                                                                  AS "Фактические часы работы",
               null                                                                                  AS "Плановые часы работы",
               null                                                                                  AS "Опоздания",
               null                                                                                  AS "Ранний уход",
               null                                                                                  AS "Вакансия",
               null                                                                                  AS is_vacancy,
               null                                                                                  AS "К-во отметок факт",
               null                                                                                  AS "К-во отметок план",
               null::character varying(150)                                                          AS "Табельный номер",
               null                                                                                  AS "Тип работ",
               null                                                                                  AS "Авт-ки созданный план",
               null                                                                                  AS "Авт-ки созданный факт",
               null::character varying(64)                                                           AS "Табельный номер трудоустройства",
               pc.user_id                                                                            AS "ID Пользователя",
               null::character varying(128)                                                          AS "Сеть Подразделения",
               null::character varying(128)                                                          AS "Сеть Сотрудника",
               null::integer                                                                         AS "Аутсорс",
               (SELECT sum(pc2.norm_hours) / COALESCE(NULLIF(count(pc2.id), 0), 1::bigint)::double precision
                FROM prod_cal pc2
                WHERE pc.employee_id = pc2.employee_id
                  and date_trunc('month'::text, pc.dt::timestamp with time zone) =
                      date_trunc('month'::text, pc2.dt::timestamp with time zone))::double precision AS "Норма часов (для суммы)"
        from prod_cal pc
        WHERE pc.dt >= '2020-01-01'::date
          AND pc.dt < (now() + '2 months'::interval);
""")
    schema_editor.execute(
        """
        CREATE OR REPLACE VIEW public.metabase_financial_stat AS
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
        """
    )
    schema_editor.execute("""\
         create or replace view prod_cal_work_hours as
         SELECT date_trunc('month'::text, pd.dt::timestamp with time zone)::date AS dt,
            employee.user_id,
            u.username,
            e.shop_id,
            s.code AS shop_code,
            sum(
                CASE
                    WHEN pd.type::text = 'W'::text THEN 8
                    WHEN pd.type::text = 'S'::text THEN 7
                    WHEN pd.type::text = 'H'::text THEN 0
                    ELSE 0
                END::double precision * COALESCE(wp.hours_in_a_week::integer, 40)::double precision / 40::double precision * e.norm_work_hours::double precision / 100::double precision) AS norm_hours,
           wtn.name as work_type_name
           FROM base_productionday pd
             JOIN base_employment e ON pd.dt >= e.dt_hired AND pd.dt <= e.dt_fired
             JOIN base_employee employee ON e.employee_id = employee.id
             JOIN base_user u ON employee.user_id = u.id
             JOIN base_shop s ON e.shop_id = s.id
             LEFT JOIN timetable_employmentworktype ewt on e.id = ewt.employment_id AND ewt.id = (
                SELECT min(ewt2.id)
                FROM timetable_employmentworktype ewt2
                inner join timetable_worktype wt2 on ewt2.work_type_id = wt2.id
                WHERE e.id = ewt2.employment_id
             )
             LEFT JOIN timetable_worktype wt on ewt.work_type_id = wt.id and wt.shop_id = e.shop_id and wt.dttm_deleted is null
             LEFT JOIN timetable_worktypename wtn on wt.work_type_name_id = wtn.id
             LEFT JOIN base_workerposition wp ON e.position_id = wp.id
          GROUP BY (date_trunc('month'::text, pd.dt::timestamp with time zone)::date), employee.user_id, u.username, e.shop_id, s.code, wtn.name;""")
    schema_editor.execute("""\
        create or replace view v_mda_users as
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
                WHEN (EXISTS ( SELECT s2.id
                   FROM base_shop s2
                  WHERE s2.id = s.id AND s2.director_id = u.id)) AND (g.code::text = 'director'::text OR fg.code::text = 'director'::text) THEN 'DIR'::text
                WHEN g.code::text = 'worker'::text AND fg.code IS NULL THEN 'MANAGER'::text
                ELSE NULL::text
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
        GREATEST(u.dttm_modified, e.dttm_modified, wp.dttm_modified) AS last_modified
       FROM base_employment e
         JOIN base_employee employee ON e.employee_id = employee.id
         JOIN base_user u ON employee.user_id = u.id
         JOIN base_shop s ON e.shop_id = s.id
         LEFT JOIN base_workerposition wp ON e.position_id = wp.id
         LEFT JOIN base_group fg ON e.function_group_id = fg.id
         LEFT JOIN base_group g ON wp.group_id = g.id
         LEFT JOIN timetable_workerday wdpa ON employee.id = wdpa.employee_id AND wdpa.dt = now()::date AND wdpa.is_fact = false AND wdpa.is_approved = true
         LEFT JOIN timetable_workerday wdpna ON employee.id = wdpna.employee_id AND wdpna.dt = now()::date AND wdpna.is_fact = false AND wdpna.is_approved = false
      WHERE (e.dttm_deleted IS NULL OR e.dttm_deleted >= (CURRENT_TIMESTAMP - '60 days'::interval)) AND (s.dttm_deleted IS NULL OR s.dttm_deleted >= (CURRENT_TIMESTAMP - '60 days'::interval)) AND (s.dt_closed IS NULL OR s.dt_closed >= (CURRENT_TIMESTAMP - '60 days'::interval)) AND e.dt_hired < e.dt_fired AND (fg.code IS NULL OR (fg.code::text <> ALL (ARRAY['admin'::text, 'controller'::text]))) AND (employee.user_id <> ALL (ARRAY[1::bigint, 2::bigint])) AND e.dt_fired > '2020-10-01'::date AND e.dt_hired <= CURRENT_TIMESTAMP::date AND (NOT wp.group_id = 3 OR wp.group_id IS NULL OR wp.group_id = 3 AND (wdpa.type IS NULL OR (wdpa.type::text <> ALL (ARRAY['M'::text, 'S'::text]))) AND (wdpna.type IS NULL OR (wdpna.type::text <> ALL (ARRAY['M'::text, 'S'::text]))));
             ;""")

class Migration(migrations.Migration):

    dependencies = [
        ('base', '0105_auto_20210528_0914'),
        ('timetable', '0071_auto_20210517_2043'),
    ]

    operations = [
        migrations.RunPython(drop_views, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='functiongroup',
            name='func',
            field=models.CharField(choices=[('AutoSettings_create_timetable', 'AutoSettings_create_timetable'), ('AutoSettings_set_timetable', 'AutoSettings_set_timetable'), ('AutoSettings_delete_timetable', 'AutoSettings_delete_timetable'), ('AuthUserView', 'AuthUserView'), ('Break', 'Break'), ('Employment', 'Employment'), ('Employee', 'Employee'), ('Employment_auto_timetable', 'Employment_auto_timetable'), ('Employment_timetable', 'Employment_timetable'), ('EmploymentWorkType', 'EmploymentWorkType'), ('ExchangeSettings', 'ExchangeSettings'), ('FunctionGroupView', 'FunctionGroupView'), ('FunctionGroupView_functions', 'FunctionGroupView_functions'), ('LoadTemplate', 'LoadTemplate'), ('LoadTemplate_apply', 'LoadTemplate_apply'), ('LoadTemplate_calculate', 'LoadTemplate_calculate'), ('LoadTemplate_download', 'LoadTemplate_download'), ('LoadTemplate_upload', 'LoadTemplate_upload'), ('Network', 'Network'), ('Notification', 'Notification'), ('OperationTemplate', 'OperationTemplate'), ('OperationTypeName', 'OperationTypeName'), ('OperationType', 'OperationType'), ('OperationTypeRelation', 'OperationTypeRelation'), ('OperationTypeTemplate', 'OperationTypeTemplate'), ('PeriodClients', 'PeriodClients'), ('PeriodClients_indicators', 'PeriodClients_indicators'), ('PeriodClients_put', 'PeriodClients_put'), ('PeriodClients_delete', 'PeriodClients_delete'), ('PeriodClients_upload', 'PeriodClients_upload'), ('PeriodClients_download', 'PeriodClients_download'), ('Receipt', 'Receipt'), ('Group', 'Group'), ('Shop', 'Shop'), ('Shop_stat', 'Shop_stat'), ('Shop_tree', 'Shop_tree'), ('Shop_outsource_tree', 'Shop_outsource_tree'), ('Subscribe', 'Subscribe'), ('TickPoint', 'TickPoint'), ('Timesheet', 'Timesheet'), ('Timesheet_stats', 'Timesheet_stats'), ('User', 'User'), ('User_change_password', 'User_change_password'), ('User_delete_biometrics', 'User_delete_biometrics'), ('WorkerConstraint', 'WorkerConstraint'), ('WorkerDay', 'WorkerDay'), ('WorkerDay_approve', 'WorkerDay_approve'), ('WorkerDay_daily_stat', 'WorkerDay_daily_stat'), ('WorkerDay_worker_stat', 'WorkerDay_worker_stat'), ('WorkerDay_vacancy', 'WorkerDay_vacancy'), ('WorkerDay_change_list', 'WorkerDay_change_list'), ('WorkerDay_copy_approved', 'WorkerDay_copy_approved'), ('WorkerDay_copy_range', 'WorkerDay_copy_range'), ('WorkerDay_duplicate', 'WorkerDay_duplicate'), ('WorkerDay_delete_worker_days', 'WorkerDay_delete_worker_days'), ('WorkerDay_exchange', 'WorkerDay_exchange'), ('WorkerDay_exchange_approved', 'WorkerDay_exchange_approved'), ('WorkerDay_confirm_vacancy', 'WorkerDay_confirm_vacancy'), ('WorkerDay_confirm_vacancy_to_worker', 'WorkerDay_confirm_vacancy_to_worker'), ('WorkerDay_reconfirm_vacancy_to_worker', 'WorkerDay_reconfirm_vacancy_to_worker'), ('WorkerDay_upload', 'WorkerDay_upload'), ('WorkerDay_upload_fact', 'WorkerDay_upload_fact'), ('WorkerDay_download_timetable', 'WorkerDay_download_timetable'), ('WorkerDay_download_tabel', 'WorkerDay_download_tabel'), ('WorkerDay_editable_vacancy', 'WorkerDay_editable_vacancy'), ('WorkerDay_approve_vacancy', 'WorkerDay_approve_vacancy'), ('WorkerDay_change_range', 'WorkerDay_change_range'), ('WorkerDay_request_approve', 'WorkerDay_request_approve'), ('WorkerDay_block', 'WorkerDay_block'), ('WorkerDay_unblock', 'WorkerDay_unblock'), ('WorkerPosition', 'WorkerPosition'), ('WorkTypeName', 'WorkTypeName'), ('WorkType', 'WorkType'), ('WorkType_efficiency', 'WorkType_efficiency'), ('ShopMonthStat', 'ShopMonthStat'), ('ShopMonthStat_status', 'ShopMonthStat_status'), ('ShopSettings', 'ShopSettings'), ('ShopSchedule', 'ShopSchedule'), ('VacancyBlackList', 'VacancyBlackList'), ('Task', 'Task'), ('signout', 'signout'), ('password_edit', 'password_edit'), ('get_worker_day_approves', 'get_worker_day_approves'), ('create_worker_day_approve', 'create_worker_day_approve'), ('delete_worker_day_approve', 'delete_worker_day_approve'), ('get_cashboxes', 'get_cashboxes'), ('get_cashboxes_info', 'get_cashboxes_info'), ('create_cashbox', 'create_cashbox'), ('update_cashbox', 'update_cashbox'), ('delete_cashbox', 'delete_cashbox'), ('get_types', 'get_types'), ('create_work_type', 'create_work_type'), ('edit_work_type', 'edit_work_type'), ('delete_work_type', 'delete_work_type'), ('get_notifications', 'get_notifications'), ('get_notifications2', 'get_notifications2'), ('set_notifications_read', 'set_notifications_read'), ('get_worker_day', 'get_worker_day'), ('delete_worker_day', 'delete_worker_day'), ('request_worker_day', 'request_worker_day'), ('set_worker_day', 'set_worker_day'), ('handle_worker_day_request', 'handle_worker_day_request'), ('get_worker_day_logs', 'get_worker_day_logs'), ('get_cashier_info', 'get_cashier_info'), ('change_cashier_info', 'change_cashier_info'), ('create_cashier', 'create_cashier'), ('get_cashiers_info', 'get_cashiers_info'), ('select_cashiers', 'select_cashiers'), ('get_not_working_cashiers_list', 'get_not_working_cashiers_list'), ('get_cashiers_list', 'get_cashiers_list'), ('change_cashier_status', 'change_cashier_status'), ('set_selected_cashiers', 'set_selected_cashiers'), ('delete_cashier', 'delete_cashier'), ('set_timetable', 'set_timetable'), ('create_timetable', 'create_timetable'), ('delete_timetable', 'delete_timetable'), ('get_cashier_timetable', 'get_cashier_timetable'), ('get_cashiers_timetable', 'get_cashiers_timetable'), ('dublicate_cashier_table', 'dublicate_cashier_table'), ('get_slots', 'get_slots'), ('get_all_slots', 'get_all_slots'), ('get_workers', 'get_workers'), ('get_outsource_workers', 'get_outsource_workers'), ('get_user_urv', 'get_user_urv'), ('upload_urv', 'upload_urv'), ('get_forecast', 'get_forecast'), ('upload_demand', 'upload_demand'), ('upload_timetable', 'upload_timetable'), ('notify_workers_about_vacancy', 'notify_workers_about_vacancy'), ('do_notify_action', 'do_notify_action'), ('get_workers_to_exchange', 'get_workers_to_exchange'), ('exchange_workers_day', 'exchange_workers_day'), ('set_demand', 'set_demand'), ('set_pred_bills', 'set_pred_bills'), ('get_operation_templates', 'get_operation_templates'), ('create_operation_template', 'create_operation_template'), ('update_operation_template', 'update_operation_template'), ('delete_operation_template', 'delete_operation_template'), ('show_vacancy', 'show_vacancy'), ('cancel_vacancy', 'cancel_vacancy'), ('confirm_vacancy', 'confirm_vacancy'), ('get_demand_xlsx', 'get_demand_xlsx'), ('get_department_stats_xlsx', 'get_department_stats_xlsx'), ('get_timetable_xlsx', 'get_timetable_xlsx'), ('get_urv_xlsx', 'get_urv_xlsx'), ('get_tabel', 'get_tabel'), ('get_department', 'get_department'), ('add_department', 'add_department'), ('edit_department', 'edit_department'), ('get_department_list', 'get_department_list'), ('get_department_stats', 'get_department_stats'), ('get_parameters', 'get_parameters'), ('set_parameters', 'set_parameters'), ('get_demand_change_logs', 'get_demand_change_logs'), ('get_table', 'get_table'), ('get_status', 'get_status'), ('get_change_request', 'get_change_request'), ('get_month_stat', 'get_month_stat'), ('get_indicators', 'get_indicators'), ('get_worker_position_list', 'get_worker_position_list'), ('set_worker_restrictions', 'set_worker_restrictions'), ('create_predbills_request', 'create_predbills_request')], max_length=128),
        ),
        migrations.AlterField(
            model_name='employment',
            name='norm_work_hours',
            field=models.FloatField(default=100),
        ),
        migrations.RunPython(create_views, migrations.RunPython.noop),
    ]
