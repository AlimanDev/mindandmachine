# Generated by Django 2.2.16 on 2021-09-16 06:01

from django.db import migrations, models

def migrate_periods(app, schema_editor):
    ReportConfig = app.get_model('reports', 'ReportConfig')
    ReportConfig.objects.filter(
        include_today=True,
    ).update(
        period_start='T',
    )

class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0006_auto_20210914_1120'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportconfig',
            name='period_start',
            field=models.CharField(choices=[('T', 'Today'), ('E', 'Yesterday'), ('M', 'End of previous month'), ('Q', 'End of previous quarter'), ('H', 'End of previous half a year'), ('Y', 'End of previous year')], default='E', max_length=1, verbose_name='Начало периода'),
        ),
        migrations.RunPython(migrate_periods),
        migrations.RemoveField(
            model_name='reportconfig',
            name='include_today',
        ),
    ]
