# Generated by Django 2.2.7 on 2020-04-06 15:28

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0016_auto_20200327_1143'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscribe',
            name='dttm_deleted',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='subscribe',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
