# Generated by Django 2.2.7 on 2019-12-04 13:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0069_merge_20191129_1226'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='work_hours',
            field=models.SmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='functiongroup',
            name='func',
            field=models.CharField(choices=[('signout', 'signout'), ('password_edit', 'password_edit'), ('get_worker_day_approves', 'get_worker_day_approves'), ('create_worker_day_approve', 'create_worker_day_approve'), ('delete_worker_day_approve', 'delete_worker_day_approve'), ('get_cashboxes', 'get_cashboxes'), ('get_cashboxes_info', 'get_cashboxes_info'), ('create_cashbox', 'create_cashbox'), ('update_cashbox', 'update_cashbox'), ('delete_cashbox', 'delete_cashbox'), ('get_types', 'get_types'), ('create_work_type', 'create_work_type'), ('edit_work_type', 'edit_work_type'), ('delete_work_type', 'delete_work_type'), ('get_notifications', 'get_notifications'), ('get_notifications2', 'get_notifications2'), ('set_notifications_read', 'set_notifications_read'), ('get_worker_day', 'get_worker_day'), ('delete_worker_day', 'delete_worker_day'), ('request_worker_day', 'request_worker_day'), ('set_worker_day', 'set_worker_day'), ('handle_worker_day_request', 'handle_worker_day_request'), ('get_worker_day_logs', 'get_worker_day_logs'), ('get_cashier_info', 'get_cashier_info'), ('change_cashier_info', 'change_cashier_info'), ('create_cashier', 'create_cashier'), ('get_cashiers_info', 'get_cashiers_info'), ('select_cashiers', 'select_cashiers'), ('get_not_working_cashiers_list', 'get_not_working_cashiers_list'), ('get_cashiers_list', 'get_cashiers_list'), ('change_cashier_status', 'change_cashier_status'), ('set_selected_cashiers', 'set_selected_cashiers'), ('delete_cashier', 'delete_cashier'), ('set_timetable', 'set_timetable'), ('create_timetable', 'create_timetable'), ('delete_timetable', 'delete_timetable'), ('get_cashier_timetable', 'get_cashier_timetable'), ('get_cashiers_timetable', 'get_cashiers_timetable'), ('dublicate_cashier_table', 'dublicate_cashier_table'), ('get_slots', 'get_slots'), ('get_all_slots', 'get_all_slots'), ('get_workers', 'get_workers'), ('get_outsource_workers', 'get_outsource_workers'), ('get_user_urv', 'get_user_urv'), ('upload_urv', 'upload_urv'), ('get_forecast', 'get_forecast'), ('upload_demand', 'upload_demand'), ('upload_timetable', 'upload_timetable'), ('notify_workers_about_vacancy', 'notify_workers_about_vacancy'), ('do_notify_action', 'do_notify_action'), ('get_workers_to_exchange', 'get_workers_to_exchange'), ('exchange_workers_day', 'exchange_workers_day'), ('set_demand', 'set_demand'), ('set_pred_bills', 'set_pred_bills'), ('get_operation_templates', 'get_operation_templates'), ('create_operation_template', 'create_operation_template'), ('update_operation_template', 'update_operation_template'), ('delete_operation_template', 'delete_operation_template'), ('show_vacancy', 'show_vacancy'), ('cancel_vacancy', 'cancel_vacancy'), ('confirm_vacancy', 'confirm_vacancy'), ('get_demand_xlsx', 'get_demand_xlsx'), ('get_department_stats_xlsx', 'get_department_stats_xlsx'), ('get_timetable_xlsx', 'get_timetable_xlsx'), ('get_urv_xlsx', 'get_urv_xlsx'), ('get_tabel', 'get_tabel'), ('get_department', 'get_department'), ('add_department', 'add_department'), ('edit_department', 'edit_department'), ('get_department_list', 'get_department_list'), ('get_department_stats', 'get_department_stats'), ('get_parameters', 'get_parameters'), ('set_parameters', 'set_parameters'), ('get_demand_change_logs', 'get_demand_change_logs'), ('get_table', 'get_table'), ('get_status', 'get_status'), ('get_change_request', 'get_change_request'), ('get_month_stat', 'get_month_stat'), ('get_indicators', 'get_indicators'), ('get_worker_position_list', 'get_worker_position_list'), ('set_worker_restrictions', 'set_worker_restrictions'), ('create_predbills_request', 'create_predbills_request')], max_length=128),
        ),
    ]
