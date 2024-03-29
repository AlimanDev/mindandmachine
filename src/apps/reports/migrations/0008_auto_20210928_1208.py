# Generated by Django 2.2.24 on 2021-09-28 12:08

from django.db import migrations, models
import django.db.models.deletion


def fill_report_config_new_period(apps, schema_editor):
    ReportConfig = apps.get_model('reports', 'ReportConfig')
    Period = apps.get_model('reports', 'Period')
    for report_config in ReportConfig.objects.all():
        new_period, _period_created = Period.objects.get_or_create(
            period=report_config.old_period,
            period_start=report_config.period_start,
            count_of_periods=report_config.count_of_periods,
        )
        report_config.period = new_period
        report_config.save()


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0007_auto_20210916_0601'),
    ]

    operations = [
        migrations.CreateModel(
            name='Period',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(blank=True, max_length=256, null=True)),
                ('count_of_periods', models.IntegerField(default=1, verbose_name='Количество периодов')),
                ('period', models.CharField(choices=[('D', 'Day'), ('M', 'Month'), ('Q', 'Quarter'), ('H', 'Half a year'), ('Y', 'Year')], default='D', max_length=1, verbose_name='Период')),
                ('period_start', models.CharField(choices=[('T', 'Today'), ('E', 'Yesterday'), ('M', 'End of previous month'), ('Q', 'End of previous quarter'), ('H', 'End of previous half a year'), ('Y', 'End of previous year')], default='E', max_length=1, verbose_name='Начало периода')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RenameField(
            model_name='reportconfig',
            old_name='period',
            new_name='old_period',
        ),
        migrations.AddField(
            model_name='reportconfig',
            name='period',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='reports.Period'),
        ),
        migrations.RunPython(fill_report_config_new_period),
        migrations.RemoveField(
            model_name='reportconfig',
            name='count_of_periods',
        ),
        migrations.RemoveField(
            model_name='reportconfig',
            name='old_period',
        ),
        migrations.RemoveField(
            model_name='reportconfig',
            name='period_start',
        ),
        migrations.AlterField(
            model_name='reportconfig',
            name='period',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='reports.Period'),
        ),
    ]
