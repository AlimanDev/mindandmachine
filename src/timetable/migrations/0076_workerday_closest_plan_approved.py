# Generated by Django 2.2.16 on 2021-08-02 21:40

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0075_auto_20210707_0735'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='closest_plan_approved',
            field=models.OneToOneField(blank=True, help_text='Используется в факте подтвержденном (созданном на основе отметок) для связи с планом подтвержденным', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='related_fact_approved', to='timetable.WorkerDay'),
        ),
    ]
