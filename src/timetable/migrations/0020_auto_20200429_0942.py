# Generated by Django 2.2.7 on 2020-04-29 09:42

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0019_merge_20200428_1454'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerconstraint',
            name='employment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='worker_constraints', to='base.Employment'),
        ),
    ]
