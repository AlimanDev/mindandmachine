# Generated by Django 2.0.5 on 2018-08-15 10:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0044_auto_20180807_0932'),
    ]

    operations = [
        # migrations.RemoveField(
        #     model_name='user',
        #     name='permissions',
        # ),
        migrations.AlterField(
            model_name='perioddemand',
            name='products',
            field=models.FloatField(default=0),
        ),
        migrations.AlterField(
            model_name='perioddemand',
            name='queue_wait_length',
            field=models.FloatField(default=0),
        ),
        migrations.AlterField(
            model_name='perioddemand',
            name='queue_wait_time',
            field=models.FloatField(default=0),
        ),
    ]