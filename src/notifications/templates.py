SYSTEM_EMAIL_TEMPLATES = [
    ('notifications/email/employee_canceled_vacancy.html', 'Сотрудник отменил вакансию'),
    ('notifications/email/employee_responded_to_the_vacancy.html', 'Сотрудник откликнулся на вакансию'),
    ('notifications/email/request_approve.html', 'Подразделение {{ shop.name }} запрашивает подтверждения графика'),
    ('notifications/email/approve.html', 'График в подразделении {{ shop.name }} подтвержден'),
    ('notifications/email/employee_not_checked.html', 'Сотрудник {{ user.last_name }} {{ user.first_name }} не отметился на {{ type }} в {{ dttm }}.'),
    ('notifications/email/employee_working_not_according_to_plan.html', 'Сотрудник {{ user.last_name }} {{ user.first_name }} вышел не по плану в {{ dttm }}.'),
    ('notifications/email/duplicate_biometrics.html', 'Одинаковые биометрические параметры сотрудников. Первый сотрудник: {{fio1}} Табельный номер: {{tabel_code1}} Ссылка на биошаблон: {{url1}} Второй сотрудник: {{fio2}} Табельный номер: {{tabel_code2}} Ссылка на биошаблон: {{url2}}'),
    ('notifications/email/vacancy_confirmed.html', 'Сотрудник {{user.last_name}} {{user.first_name}} откликнулся на вакансию {{dt}} с типом работ {{work_type}}'),
    ('notifications/email/vacancy_created.html', 'В отделе {{shop_name}} автомтически создана вакансия на {{dt}} с {{dttm_from}} по {{dttm_to}} для типа работ {{work_type}}'),
    ('notifications/email/vacancy_deleted.html', 'В отделе {{shop_name}} отменена вакансия у сотрудника {{last_name}} {{first_name}} с табельным номером {{tabel_code}} | без сотрудника на {{dt}} с {{dttm_from}} по {{dttm_to}}'),
]
