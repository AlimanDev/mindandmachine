SYSTEM_EMAIL_TEMPLATES = [
    ('notifications/email/employee_canceled_vacancy.html', 'Сотрудник отменил вакансию'),
    ('notifications/email/employee_responded_to_the_vacancy.html', 'Сотрудник откликнулся на вакансию'),
    ('notifications/email/request_approve.html', 'Подразделение {{ shop.name }} запрашивает подтверждения графика'),
    ('notifications/email/approve.html', 'График в подразделении {{ shop.name }} подтвержден'),
    ('notifications/email/employee_not_checked_in.html', 'Сотрудник {{ user.last_name }} {{ user.first_name }} не отметился на {{ type }} в {{ dttm }}.'),
    ('notifications/email/employee_working_not_according_to_plan.html', 'Сотрудник {{ user.last_name }} {{ user.first_name }} вышел не по плану в {{ dttm }}.'),
    ('notifications/email/duplicate_biometrics.html', 'Одинаковые биометрические параметры сотрудников. Первый сотрудник: {{fio1}} Табельный номер: {{tabel_code1}} Ссылка на биошаблон: {{url1}} Второй сотрудник: {{fio2}} Табельный номер: {{tabel_code2}} Ссылка на биошаблон: {{url2}}'),
]
