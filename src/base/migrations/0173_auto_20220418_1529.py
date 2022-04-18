# Generated by Django 3.2.9 on 2022-04-18 15:29

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0172_alter_functiongroup_func'),
    ]

    operations = [
        migrations.AddField(
            model_name='employment',
            name='sawh_settings',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='base.sawhsettings', verbose_name='Настройка нормы', related_name='employments'),
        ),
        migrations.AddField(
            model_name='sawhsettingsmapping',
            name='work_hours_by_months',
            field=models.JSONField(blank=True, null=True, verbose_name='Настройки по распределению часов в рамках года'),
        ),
        migrations.AlterField(
            model_name='functiongroup',
            name='func',
            field=models.CharField(choices=[('AttendanceRecords', 'Отметка (attendance_records)'), ('AttendanceRecords_report', 'Отчет по отметкам (Получить) (attendance_records/report/)'), ('AutoSettings_create_timetable', 'Составление графика (Создать) (auto_settings/create_timetable/)'), ('AutoSettings_set_timetable', 'Задать график (ответ от алгоритмов, Создать) (auto_settings/set_timetable/)'), ('AutoSettings_delete_timetable', 'Удалить график (Создать) (auto_settings/delete_timetable/)'), ('AuthUserView', 'Получить авторизованного пользователя (auth/user/)'), ('Break', 'Перерыв (break)'), ('ContentBlock', 'Блок контента (content_block)'), ('Employment', 'Трудоустройство (employment)'), ('Employee', 'Сотрудник (employee)'), ('Employee_shift_schedule', 'Графики смен сотрудников (employee/shift_schedule/)'), ('Employment_auto_timetable', 'Выбрать сорудников для автосоставления (Создать) (employment/auto_timetable/)'), ('Employment_timetable', 'Редактирование полей трудоустройства, связанных с расписанием (employment/timetable/)'), ('EmploymentWorkType', 'Связь трудоустройства и типа работ (employment_work_type)'), ('Employment_batch_update_or_create', 'Массовое создание/обновление трудоустройств (Создать/Обновить) (employment/batch_update_or_create/)'), ('ExchangeSettings', 'Настройки обмена сменами (exchange_settings)'), ('FunctionGroupView', 'Доступ к функциям (function_group)'), ('FunctionGroupView_functions', 'Получить список доступных функций (Получить) (function_group/functions/)'), ('LoadTemplate', 'Шаблон нагрузки (load_template)'), ('LoadTemplate_apply', 'Применить шаблон нагрузки (Создать) (load_template/apply/)'), ('LoadTemplate_calculate', 'Рассчитать нагрузку (Создать) (load_template/calculate/)'), ('LoadTemplate_download', 'Скачать шаблон нагрузки (Получить) (load_template/download/)'), ('LoadTemplate_upload', 'Загрузить шаблон нагрузки (Создать) (load_template/upload/)'), ('Network', 'Сеть (network)'), ('OperationTypeName', 'Название типа операции (operation_type_name)'), ('OperationType', 'Тип операции (operation_type)'), ('OperationTypeRelation', 'Отношение типов операций (operation_type_relation)'), ('OperationTypeTemplate', 'Шаблон типа операции (operation_type_template)'), ('PeriodClients', 'Нагрузка (timeserie_value)'), ('PeriodClients_indicators', 'Индикаторы нагрузки (Получить) (timeserie_value/indicators/)'), ('PeriodClients_put', 'Обновить нагрузку (Обновить) (timeserie_value/put/)'), ('PeriodClients_delete', 'Удалить нагрузку (Удалить) (timeserie_value/delete/)'), ('PeriodClients_upload', 'Загрузить нагрузку (Создать) (timeserie_value/upload/)'), ('PeriodClients_upload_demand', 'Загрузить нагрузку по магазинам (Создать) (timeserie_value/upload_demand/)'), ('PeriodClients_download', 'Скачать нагрузку (Получить) (timeserie_value/download/)'), ('Receipt', 'Чек (receipt)'), ('Reports_pivot_tabel', 'Скачать сводный табель (Получить) (report/pivot_tabel/)'), ('Reports_schedule_deviation', 'Скачать отчет по отклонениям от планового графика (Получить) (report/schedule_deviation/)'), ('Reports_consolidated_timesheet_report', 'Скачать "Консолидированный отчет об отработанном времени" (Получить) (report/consolidated_timesheet_report/)'), ('Group', 'Группа доступа (group)'), ('Shop', 'Отдел (department)'), ('Shop_stat', 'Статистика по отделам (Получить) (department/stat/)'), ('Shop_tree', 'Дерево отделов (Получить) (department/tree/)'), ('Shop_internal_tree', 'Дерево отделов сети пользователя (Получить) (department/internal_tree/)'), ('Shop_load_template', 'Изменить шаблон нагрузки магазина (Обновить) (department/{pk}/load_template/)'), ('Shop_outsource_tree', 'Дерево отделов клиентов (для аутсорс компаний) (Получить) (department/outsource_tree/)'), ('TickPoint', 'Точка отметки (tick_points)'), ('Timesheet', 'Табель (timesheet)'), ('Timesheet_stats', 'Статистика табеля (Получить) (timesheet/stats/)'), ('Timesheet_recalc', 'Запустить пересчет табеля (Создать) (timesheet/recalc/)'), ('Timesheet_lines', 'Табель построчно (Получить) (timesheet/lines/)'), ('Timesheet_items', 'Сырые данные табеля (Получить) (timesheet/items/)'), ('User', 'Пользователь (user)'), ('User_change_password', 'Сменить пароль пользователю (Создать) (auth/password/change/)'), ('User_delete_biometrics', 'Удалить биометрию пользователя (Создать) (user/delete_biometrics/)'), ('User_add_biometrics', 'Добавить биометрию пользователя (Создать) (user/add_biometrics/)'), ('WorkerConstraint', 'Ограничения сотрудника (worker_constraint)'), ('WorkerDay', 'Рабочий день (worker_day)'), ('WorkerDay_approve', 'Подтвердить график (Создать) (worker_day/approve/)'), ('WorkerDay_daily_stat', 'Статистика по дням (Получить) (worker_day/daily_stat/)'), ('WorkerDay_worker_stat', 'Статистика по работникам (Получить) (worker_day/worker_stat/)'), ('WorkerDay_vacancy', 'Список вакансий (Получить) (worker_day/vacancy/)'), ('WorkerDay_change_list', 'Редактирование дней списоком (Создать) (worker_day/change_list)'), ('WorkerDay_copy_approved', 'Копировать рабочие дни из разных версий (Создать) (worker_day/copy_approved/)'), ('WorkerDay_copy_range', 'Копировать дни на следующий месяц (Создать) (worker_day/copy_range/)'), ('WorkerDay_duplicate', 'Копировать рабочие дни как ячейки эксель (Создать) (worker_day/duplicate/)'), ('WorkerDay_delete_worker_days', 'Удалить рабочие дни (Создать) (worker_day/delete_worker_days/)'), ('WorkerDay_exchange', 'Обмен сменами (Создать) (worker_day/exchange/)'), ('WorkerDay_exchange_approved', 'Обмен подтвержденными сменами (Создать) (worker_day/exchange_approved/)'), ('WorkerDay_confirm_vacancy', 'Откликнуться вакансию (Создать) (worker_day/confirm_vacancy/)'), ('WorkerDay_confirm_vacancy_to_worker', 'Назначить работника на вакансию (Создать) (worker_day/confirm_vacancy_to_worker/)'), ('WorkerDay_refuse_vacancy', 'Отказаться от вакансии (Создать) (worker_day/refuse_vacancy/)'), ('WorkerDay_reconfirm_vacancy_to_worker', 'Переназначить работника на вакансию (Создать) (worker_day/reconfirm_vacancy_to_worker/)'), ('WorkerDay_upload', 'Загрузить плановый график (Создать) (worker_day/upload/)'), ('WorkerDay_upload_fact', 'Загрузить фактический график (Создать) (worker_day/upload_fact/)'), ('WorkerDay_download_timetable', 'Скачать плановый график (Получить) (worker_day/download_timetable/)'), ('WorkerDay_download_tabel', 'Скачать табель (Получить) (worker_day/download_tabel/)'), ('WorkerDay_editable_vacancy', 'Получить редактируемую вакансию (Получить) (worker_day/{pk}/editable_vacancy/)'), ('WorkerDay_approve_vacancy', 'Подтвердить вакансию (Создать) (worker_day/{pk}/approve_vacancy/)'), ('WorkerDay_change_range', 'Создание/обновление дней за период (Создать) (worker_day/change_range/)'), ('WorkerDay_request_approve', 'Запросить подтверждение графика (Создать) (worker_day/request_approve/)'), ('WorkerDay_block', 'Заблокировать рабочий день (Создать) (worker_day/block/)'), ('WorkerDay_unblock', 'Разблокировать рабочий день (Создать) (worker_day/unblock/)'), ('WorkerDay_generate_upload_example', 'Скачать шаблон графика (Получить) (worker_day/generate_upload_example/)'), ('WorkerDay_recalc', 'Пересчитать часы (Создать) (worker_day/recalc/)'), ('WorkerDay_overtimes_undertimes_report', 'Скачать отчет о переработках/недоработках (Получить) (worker_day/overtimes_undertimes_report/)'), ('WorkerDay_batch_update_or_create', 'Массовое создание/обновление дней сотрудников (Создать/Обновить) (worker_day/batch_update_or_create/)'), ('WorkerDayType', 'Тип дня сотрудника (worker_day_type)'), ('WorkerPosition', 'Должность (worker_position)'), ('WorkTypeName', 'Название типа работ (work_type_name)'), ('WorkType', 'Тип работ ()work_type'), ('WorkType_efficiency', 'Покрытие (Получить) (work_type/efficiency/)'), ('ShopMonthStat', 'Статистика по магазину на месяц (shop_month_stat)'), ('ShopMonthStat_status', 'Статус составления графика (Получить) (shop_month_stat/status/)'), ('ShopSettings', 'Настройки автосоставления (shop_settings)'), ('ShopSchedule', 'Расписание магазина (schedule)'), ('VacancyBlackList', 'Черный список для вакансий (vacancy_black_list)'), ('Task', 'Задача (task)'), ('ShiftSchedule_batch_update_or_create', 'Массовое создание/обновление графиков работ (Создать/Обновить) (shift_schedule/batch_update_or_create/)'), ('ShiftScheduleInterval_batch_update_or_create', 'Массовое создание/обновление интервалов графиков работ сотрудников (Создать/Обновить) (shift_schedule/batch_update_or_create/)'), ('MedicalDocumentType', 'Тип медицинского документа (medical_document_type)'), ('MedicalDocument', 'Период актуальности медицинского документа (medical_document)')], help_text='В скобках указывается метод с которым работает данная функция', max_length=128),
        ),
        migrations.AlterField(
            model_name='sawhsettings',
            name='work_hours_by_months',
            field=models.JSONField(blank=True, null=True, verbose_name='Настройки по распределению часов'),
        ),
    ]
