# Generated by Django 2.2.7 on 2020-09-24 06:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0026_merge_20200918_0539'),
    ]

    operations = [
        migrations.AddField(
            model_name='loadtemplate',
            name='forecast_params',
            field=models.TextField(default='{}'),
        ),
    ]
