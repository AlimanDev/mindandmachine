# Generated by Django 2.2.16 on 2020-12-21 06:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0034_auto_20201216_0910'),
    ]

    operations = [
        migrations.AddField(
            model_name='loadtemplate',
            name='round_delta',
            field=models.FloatField(default=0),
        ),
    ]
