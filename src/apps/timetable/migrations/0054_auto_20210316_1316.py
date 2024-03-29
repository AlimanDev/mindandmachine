# Generated by Django 2.2.16 on 2021-03-16 13:16

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

def set_last_edited_by(app, schema_editor):
    WorkerDay = app.get_model('timetable', 'WorkerDay')
    WorkerDay.objects.all().update(
        last_edited_by=models.F('created_by'),
    )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('timetable', '0053_merge_20210305_1435'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='last_edited_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='user_edited', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='attendancerecords',
            name='type',
            field=models.CharField(choices=[('C', 'coming'), ('L', 'leaving'), ('S', 'break start'), ('E', 'break_end'), ('N', 'no_type')], max_length=1),
        ),
        migrations.RunPython(set_last_edited_by),
    ]
