# Generated by Django 2.0.5 on 2019-06-18 13:12

from django.db import migrations, models
import django.db.models.deletion
import django.db.models.manager


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0029_auto_20190322_1335'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('text', models.CharField(max_length=256)),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Shop')),
                ('to_workerday', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDay')),
            ],
            managers=[
                ('object', django.db.models.manager.Manager()),
            ],
        ),
        migrations.RemoveField(
            model_name='notifications',
            name='content_type',
        ),
        migrations.RemoveField(
            model_name='notifications',
            name='object_id',
        ),
        migrations.RemoveField(
            model_name='notifications',
            name='text',
        ),
        migrations.RemoveField(
            model_name='notifications',
            name='type',
        ),
        migrations.AlterField(
            model_name='functiongroup',
            name='func',
            field=models.CharField(choices=[('get_cashboxes_open_time', 'get_cashboxes_open_time'), ('get_workers', 'get_workers'), ('get_demand_change_logs', 'get_demand_change_logs'), ('edit_work_type', 'edit_work_type'), ('get_cashboxes_used_resource', 'get_cashboxes_used_resource'), ('get_notifications', 'get_notifications'), ('get_notifications2', 'get_notifications2'), ('get_cashboxes_info', 'get_cashboxes_info'), ('get_department', 'get_department'), ('update_cashbox', 'update_cashbox'), ('delete_work_type', 'delete_work_type'), ('get_outsource_workers', 'get_outsource_workers'), ('add_supershop', 'add_supershop'), ('change_cashier_info', 'change_cashier_info'), ('get_demand_xlsx', 'get_demand_xlsx'), ('get_not_working_cashiers_list', 'get_not_working_cashiers_list'), ('get_table', 'get_table'), ('get_worker_day', 'get_worker_day'), ('create_cashbox', 'create_cashbox'), ('set_worker_day', 'set_worker_day'), ('signout', 'signout'), ('create_timetable', 'create_timetable'), ('get_regions', 'get_regions'), ('get_slots', 'get_slots'), ('get_user_urv', 'get_user_urv'), ('get_cashboxes', 'get_cashboxes'), ('get_cashier_timetable', 'get_cashier_timetable'), ('select_cashiers', 'select_cashiers'), ('request_worker_day', 'request_worker_day'), ('add_outsource_workers', 'add_outsource_workers'), ('get_parameters', 'get_parameters'), ('set_worker_restrictions', 'set_worker_restrictions'), ('create_cashier', 'create_cashier'), ('get_urv_xlsx', 'get_urv_xlsx'), ('get_cashiers_info', 'get_cashiers_info'), ('create_work_type', 'create_work_type'), ('get_visitors_info', 'get_visitors_info'), ('get_time_distribution', 'get_time_distribution'), ('set_queue', 'set_queue'), ('set_notifications_read', 'set_notifications_read'), ('get_status', 'get_status'), ('get_forecast', 'get_forecast'), ('set_parameters', 'set_parameters'), ('get_cashiers_list', 'get_cashiers_list'), ('get_change_request', 'get_change_request'), ('delete_timetable', 'delete_timetable'), ('get_types', 'get_types'), ('get_supershop_stats', 'get_supershop_stats'), ('get_all_slots', 'get_all_slots'), ('get_cashiers_timetable', 'get_cashiers_timetable'), ('set_demand', 'set_demand'), ('dublicate_cashier_table', 'dublicate_cashier_table'), ('get_month_stat', 'get_month_stat'), ('handle_worker_day_request', 'handle_worker_day_request'), ('get_workers_to_exchange', 'get_workers_to_exchange'), ('get_tabel', 'get_tabel'), ('delete_cashier', 'delete_cashier'), ('get_worker_day_logs', 'get_worker_day_logs'), ('password_edit', 'password_edit'), ('get_cashier_info', 'get_cashier_info'), ('change_cashier_status', 'change_cashier_status'), ('set_selected_cashiers', 'set_selected_cashiers'), ('get_indicators', 'get_indicators'), ('upload_demand', 'upload_demand'), ('upload_timetable', 'upload_timetable'), ('change_user_urv', 'change_user_urv'), ('get_super_shop', 'get_super_shop'), ('delete_cashbox', 'delete_cashbox'), ('set_timetable', 'set_timetable'), ('get_super_shop_list', 'get_super_shop_list'), ('delete_worker_day', 'delete_worker_day'), ('create_predbills_request', 'create_predbills_request'), ('get_timetable_xlsx', 'get_timetable_xlsx'), ('process_forecast', 'process_forecast'), ('edit_supershop', 'edit_supershop'), ('get_supershops_stats', 'get_supershops_stats'), ('edit_shop', 'edit_shop'), ('add_shop', 'add_shop'), ('notify_workers_about_vacancy', 'notify_workers_about_vacancy')], max_length=128),
        ),
        migrations.AlterField(
            model_name='workerdaycashboxdetails',
            name='worker_day',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDay'),
        ),
        migrations.AddField(
            model_name='notifications',
            name='event',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Event'),
        ),
    ]