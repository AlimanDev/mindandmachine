# Generated by Django 2.2.16 on 2021-07-22 09:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0004_auto_20210722_0546'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportconfig',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='Активен'),
        ),
        migrations.AlterField(
            model_name='reportconfig',
            name='report_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='reports.ReportType', verbose_name='Тип отчета'),
        ),
    ]
