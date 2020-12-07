# Generated by Django 2.2.7 on 2020-12-07 22:48

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('events', '0001_initial'),
        ('base', '0069_auto_20201207_2248'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SmtpServerSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('dttm_added', models.DateTimeField(default=django.utils.timezone.now)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128, verbose_name='Имя')),
                ('email_default_from', models.CharField(blank=True, max_length=100, null=True, verbose_name='from:')),
                ('email_host', models.CharField(blank=True, max_length=100, null=True, verbose_name='Хост')),
                ('email_port', models.IntegerField(blank=True, null=True, verbose_name='Порт')),
                ('email_username', models.CharField(blank=True, max_length=100, null=True, verbose_name='Имя пользователя')),
                ('email_password', models.CharField(blank=True, max_length=100, null=True, verbose_name='Пароль')),
                ('email_use_ssl', models.BooleanField(default=False, verbose_name='Использовать SSL')),
                ('email_use_tls', models.BooleanField(default=False, verbose_name='Использовать TLS')),
                ('email_fail_silently', models.BooleanField(default=False, verbose_name='Тихое подавление ошибок')),
                ('email_timeout', models.IntegerField(blank=True, null=True, verbose_name='Тайм-аут')),
                ('email_ssl_certfile', models.FileField(blank=True, max_length=500, null=True, upload_to='SmtpEmailBackend/certfile/%Y/%m/%d', verbose_name='Сертификат')),
                ('email_ssl_keyfile', models.FileField(blank=True, max_length=500, null=True, upload_to='SmtpEmailBackend/keyfile/%Y/%m/%d', verbose_name='Файл ключа')),
            ],
            options={
                'verbose_name': 'Настройки SMTP-сервера',
                'verbose_name_plural': 'Настройки SMTP-сервера',
            },
        ),
        migrations.CreateModel(
            name='WebhookSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128, verbose_name='Имя')),
            ],
            options={
                'verbose_name': 'Настройки WebHook',
                'verbose_name_plural': 'Настройки WebHook',
            },
        ),
        migrations.CreateModel(
            name='EventWebhookNotification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('event_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.EventType', verbose_name='Тип события')),
                ('webhook_notification_settings', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='notifications.WebhookSettings', verbose_name='Настройки webhook оповещений')),
            ],
            options={
                'verbose_name': 'Webhook оповещение о событиях',
                'verbose_name_plural': 'Webhook оповещения о событиях',
            },
        ),
        migrations.CreateModel(
            name='EventOnlineNotification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('get_recipients_from_event_type', models.BooleanField(default=False, help_text='Использовать жесткий алгоритм определения получателей, привязаный к событию и его контексту (работает только для захардкоженных событий)', verbose_name='Получать пользователей из события')),
                ('shop_ancestors', models.BooleanField(default=False, verbose_name='Искать получателей среди пользователей магазинов предков')),
                ('shop_descendants', models.BooleanField(default=False, verbose_name='Искать получателей среди пользователей магазинов потомков')),
                ('event_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.EventType', verbose_name='Тип события')),
                ('groups', models.ManyToManyField(blank=True, related_name='_eventonlinenotification_groups_+', to='base.Group', verbose_name='Оповещать пользователей определенных групп')),
                ('shop_groups', models.ManyToManyField(blank=True, related_name='_eventonlinenotification_shop_groups_+', to='base.Group', verbose_name='Оповещать пользователей магазина, имеющих выбранные группы')),
                ('users', models.ManyToManyField(blank=True, to=settings.AUTH_USER_MODEL, verbose_name='Оповещать конкретных пользователей')),
            ],
            options={
                'verbose_name': 'Онлайн оповещение о событие',
                'verbose_name_plural': 'Онлайн оповещения о событиях',
            },
        ),
        migrations.CreateModel(
            name='EventEmailNotification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('get_recipients_from_event_type', models.BooleanField(default=False, help_text='Использовать жесткий алгоритм определения получателей, привязаный к событию и его контексту (работает только для захардкоженных событий)', verbose_name='Получать пользователей из события')),
                ('shop_ancestors', models.BooleanField(default=False, verbose_name='Искать получателей среди пользователей магазинов предков')),
                ('shop_descendants', models.BooleanField(default=False, verbose_name='Искать получателей среди пользователей магазинов потомков')),
                ('email_addresses', models.CharField(blank=True, max_length=256, null=True, verbose_name='E-mail адреса получателей, через запятую')),
                ('system_email_template', models.CharField(blank=True, choices=[('employee_canceled_vacancy.html', 'Сотрудник отменил вакансию'), ('employee_responded_to_the_vacancy.html', 'Сотрудник откликнулся на вакансию')], max_length=256, null=True, verbose_name='Системный E-mail шаблон')),
                ('custom_email_template', models.TextField(blank=True, null=True, verbose_name='Пользовательский E-mail шаблон')),
                ('event_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.EventType', verbose_name='Тип события')),
                ('groups', models.ManyToManyField(blank=True, related_name='_eventemailnotification_groups_+', to='base.Group', verbose_name='Оповещать пользователей определенных групп')),
                ('shop_groups', models.ManyToManyField(blank=True, related_name='_eventemailnotification_shop_groups_+', to='base.Group', verbose_name='Оповещать пользователей магазина, имеющих выбранные группы')),
                ('smtp_server_settings', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='notifications.SmtpServerSettings', verbose_name='Настройки smtp-сервера')),
                ('users', models.ManyToManyField(blank=True, to=settings.AUTH_USER_MODEL, verbose_name='Оповещать конкретных пользователей')),
            ],
            options={
                'verbose_name': 'Email оповещение о событиях',
                'verbose_name_plural': 'Email оповещения о событиях',
            },
        ),
    ]
