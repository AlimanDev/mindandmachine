# Generated by Django 2.2.16 on 2021-08-11 17:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0120_auto_20210810_1506'),
    ]

    operations = [
        migrations.AlterField(
            model_name='functiongroup',
            name='func',
            field=models.CharField(choices=[('AttendanceRecords', 'Отметка'), ('AttendanceRecords_report', 'Отчет по отметкам (Получить)'), ('AutoSettings_create_timetable', 'Составление графика (Создать)'), ('AutoSettings_set_timetable', 'Задать график (ответ от алгоритмов, Создать)'), ('AutoSettings_delete_timetable', 'Удалить график (Создать)'), ('AuthUserView', 'Получить авторизованного пользователя'), ('Break', 'Перерыв'), ('Employment', 'Трудоустройство'), ('Employee', 'Сотрудник'), ('Employment_auto_timetable', 'Выбрать сорудников для автосоставления (Создать)'), ('Employment_timetable', 'Редактирование полей трудоустройства, связанных с расписанием'), ('EmploymentWorkType', 'Связь трудоустройства и типа работ'), ('ExchangeSettings', 'Настройки обмена сменами'), ('FunctionGroupView', 'Доступ к функциям'), ('FunctionGroupView_functions', 'Получить список доступных функций (Получить)'), ('LoadTemplate', 'Шаблон нагрузки'), ('LoadTemplate_apply', 'Применить шаблон нагрузки (Создать)'), ('LoadTemplate_calculate', 'Рассчитать нагрузку (Создать)'), ('LoadTemplate_download', 'Скачать шаблон нагрузки (Получить)'), ('LoadTemplate_upload', 'Загрузить шаблон нагрузки (Создать)'), ('Network', 'Сеть'), ('Notification', 'Уведомление'), ('OperationTemplate', 'Шаблон операции'), ('OperationTypeName', 'Название типа операции'), ('OperationType', 'Тип операции'), ('OperationTypeRelation', 'Отношение типов операций'), ('OperationTypeTemplate', 'Шаблон типа операции'), ('PeriodClients', 'Нагрузка'), ('PeriodClients_indicators', 'Индикаторы нагрузки (Получить)'), ('PeriodClients_put', 'Обновить нагрузку (Обновить)'), ('PeriodClients_delete', 'Удалить нагрузку (Удалить)'), ('PeriodClients_upload', 'Загрузить нагрузку (Создать)'), ('PeriodClients_download', 'Скачать нагрузку (Получить)'), ('Receipt', 'Чек'), ('Group', 'Группа доступа'), ('Shop', 'Отдел'), ('Shop_stat', 'Статистика по отделам (Получить)'), ('Shop_tree', 'Дерево отделов (Получить)'), ('Shop_outsource_tree', 'Дерево отделов клиентов (для аутсорс компаний) (Получить)'), ('Subscribe', 'Subscribe'), ('TickPoint', 'Точка отметки'), ('Timesheet', 'Табель'), ('Timesheet_stats', 'Статистика табеля (Получить)'), ('Timesheet_recalc', 'Запустить пересчет табеля (Создать)'), ('User', 'Пользователь'), ('User_change_password', 'Сменить пароль пользователю (Создать)'), ('User_delete_biometrics', 'Удалить биометрию пользователя (Создать)'), ('User_add_biometrics', 'Добавить биометрию пользователя (Создать)'), ('WorkerConstraint', 'Ограничения сотрудника'), ('WorkerDay', 'Рабочий день'), ('WorkerDay_approve', 'Подтвердить график (Создать)'), ('WorkerDay_daily_stat', 'Статистика по дням (Получить)'), ('WorkerDay_worker_stat', 'Статистика по работникам (Получить)'), ('WorkerDay_vacancy', 'Список вакансий (Получить)'), ('WorkerDay_change_list', 'Редактирование дней списоком (Создать)'), ('WorkerDay_copy_approved', 'Копировать рабочие дни из разных версий (Создать)'), ('WorkerDay_copy_range', 'Копировать дни на следующий месяц (Создать)'), ('WorkerDay_duplicate', 'Копировать рабочие дни как ячейки эксель (Создать)'), ('WorkerDay_delete_worker_days', 'Удалить рабочие дни (Создать)'), ('WorkerDay_exchange', 'Обмен сменами (Создать)'), ('WorkerDay_exchange_approved', 'Обмен подтвержденными сменами (Создать)'), ('WorkerDay_confirm_vacancy', 'Откликнуться вакансию (Создать)'), ('WorkerDay_confirm_vacancy_to_worker', 'Назначить работника на вакансию (Создать)'), ('WorkerDay_reconfirm_vacancy_to_worker', 'Переназначить работника на вакансию (Создать)'), ('WorkerDay_upload', 'Загрузить плановый график (Создать)'), ('WorkerDay_upload_fact', 'Загрузить фактический график (Создать)'), ('WorkerDay_download_timetable', 'Скачать плановый график (Получить)'), ('WorkerDay_download_tabel', 'Скачать табель (Получить)'), ('WorkerDay_editable_vacancy', 'Получить редактируемую вакансию (Получить)'), ('WorkerDay_approve_vacancy', 'Подтвердить вакансию (Создать)'), ('WorkerDay_change_range', 'Создание/обновление дней за период (Создать)'), ('WorkerDay_request_approve', 'Запросить подтверждение графика (Создать)'), ('WorkerDay_block', 'Заблокировать рабочий день (Создать)'), ('WorkerDay_unblock', 'Разблокировать рабочий день (Создать)'), ('WorkerDay_generate_upload_example', 'Скачать шаблон графика (Получить)'), ('WorkerDay_recalc', 'Пересчитать часы (Создать)'), ('WorkerDay_batch_update_or_create', 'Массовое создание/обновление дней сотрудников (Создать/Обновить)'), ('WorkerPosition', 'Должность'), ('WorkTypeName', 'Название типа работ'), ('WorkType', 'Тип работ'), ('WorkType_efficiency', 'Покрытие (Получить)'), ('ShopMonthStat', 'Статистика по магазину на месяц'), ('ShopMonthStat_status', 'Статус составления графика (Получить)'), ('ShopSettings', 'Настройки автосоставления'), ('ShopSchedule', 'Расписание магазина'), ('VacancyBlackList', 'Черный список для вакансий'), ('Task', 'Задача')], help_text='В скобках указывается метод с которым работает данная функция', max_length=128),
        ),
    ]