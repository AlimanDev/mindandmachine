# Generated by Django 2.2.3 on 2019-07-30 13:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recognition', '0010_auto_20190730_1254'),
    ]

    operations = [
        migrations.AddField(
            model_name='tickpoint',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
