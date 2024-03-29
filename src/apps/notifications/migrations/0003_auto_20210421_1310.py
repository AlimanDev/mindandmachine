# Generated by Django 2.2.16 on 2021-04-21 13:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_auto_20210209_0844'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventemailnotification',
            name='system_email_template',
            field=models.CharField(blank=True, choices=[('notifications/email/employee_canceled_vacancy.html', 'Сотрудник отменил вакансию'), ('notifications/email/employee_responded_to_the_vacancy.html', 'Сотрудник откликнулся на вакансию'), ('notifications/email/request_approve.html', 'Подразделение {{ shop.name }} запрашивает подтверждения графика'), ('notifications/email/approve.html', 'График в подразделении {{ shop.name }} подтвержден'), ('notifications/email/employee_not_checked_in.html', 'Сотрудник {{ user.last_name }} {{ user.first_name }} не отметился на {{ type }} в {{ dttm }}.'), ('notifications/email/employee_working_not_according_to_plan.html', 'Сотрудник {{ user.last_name }} {{ user.first_name }} вышел не по плану в {{ dttm }}.')], max_length=256, null=True, verbose_name='Системный E-mail шаблон'),
        ),
    ]
