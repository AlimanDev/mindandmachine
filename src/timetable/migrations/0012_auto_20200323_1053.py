# Generated by Django 2.2.7 on 2020-03-23 10:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0013_auto_20200323_1053'),
        ('timetable', '0011_auto_20200318_1410'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmploymentWorkType',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('period', models.PositiveIntegerField(default=90)),
                ('mean_speed', models.FloatField(default=1)),
                ('bills_amount', models.PositiveIntegerField(default=0)),
                ('priority', models.IntegerField(default=0)),
                ('duration', models.FloatField(default=0)),
                ('employment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_types', to='base.Employment')),
                ('work_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkType')),
            ],
            options={
                'verbose_name': 'Информация по сотруднику-типу работ',
                'unique_together': {('employment', 'work_type')},
            },
        ),
        migrations.AddField(
            model_name='workerdaycashboxdetails',
            name='event',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='worker_day_details', to='base.Event'),
        ),
        migrations.AlterField(
            model_name='event',
            name='workerday_details',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='events', to='timetable.WorkerDayCashboxDetails'),
        ),
        migrations.DeleteModel(
            name='WorkerWorkType',
        ),
    ]
