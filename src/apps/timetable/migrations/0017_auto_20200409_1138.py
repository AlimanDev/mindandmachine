# Generated by Django 2.2.7 on 2020-04-09 11:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0016_merge_20200407_1036'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerdaycashboxdetails',
            name='event',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='worker_day_details', to='base.Event'),
        ),
    ]