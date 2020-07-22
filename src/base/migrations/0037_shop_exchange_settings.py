# Generated by Django 2.2.7 on 2020-07-02 13:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0027_auto_20200702_1318'),
        ('base', '0036_workerposition_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='shop',
            name='exchange_settings',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shops', to='timetable.ExchangeSettings'),
        ),
    ]