# Generated by Django 3.2.9 on 2022-01-27 23:25

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import src.util.mixins.bulk_update_or_create


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('base', '0165_network_analytics_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=256)),
                ('tenant_id', models.CharField(max_length=128)),
                ('client_id', models.CharField(max_length=128)),
                ('client_secret', models.CharField(max_length=128)),
                ('workspace_id', models.CharField(max_length=128)),
                ('report_id', models.CharField(max_length=512)),
            ],
            options={
                'verbose_name': 'Отчет',
                'verbose_name_plural': 'Отчеты',
            },
            bases=(src.util.mixins.bulk_update_or_create.BatchUpdateOrCreateModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='ReportPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('group', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='base.group')),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pbi.report')),
                ('user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Доступ к отчету',
                'verbose_name_plural': 'Доступы к отчетам',
            },
            bases=(src.util.mixins.bulk_update_or_create.BatchUpdateOrCreateModelMixin, models.Model),
        ),
    ]
