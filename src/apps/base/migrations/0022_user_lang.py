# Generated by Django 2.2.7 on 2020-04-09 16:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0021_auto_20200408_1751'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='lang',
            field=models.CharField(default='ru', max_length=2),
        ),
    ]
