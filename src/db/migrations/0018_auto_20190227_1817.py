# Generated by Django 2.0.5 on 2019-02-27 18:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0017_merge_20190214_0744'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='comment',
        ),
        migrations.AlterField(
            model_name='user',
            name='salary',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
    ]