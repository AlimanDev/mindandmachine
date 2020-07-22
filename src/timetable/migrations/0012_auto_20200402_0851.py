# Generated by Django 2.2.7 on 2020-04-02 08:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0013_auto_20200402_0851'),
        ('timetable', '0011_auto_20200318_1410'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerconstraint',
            name='employment',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='worker_constraints', to='base.Employment'),
        ),
        migrations.AlterField(
            model_name='employmentworktype',
            name='employment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='work_types', to='base.Employment'),
        ),
        migrations.AlterUniqueTogether(
            name='workerconstraint',
            unique_together={('employment', 'weekday', 'tm')},
        ),
    ]