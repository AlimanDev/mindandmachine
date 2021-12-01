# Generated by Django 3.2.9 on 2021-11-26 08:57

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0106_auto_20211112_0838'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='cost_per_hour',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=6, verbose_name='Стоимость работ за час'),
        ),
        migrations.AddField(
            model_name='worktype',
            name='preliminary_cost_per_hour',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=6, verbose_name='Предварительная стоимость работ за час'),
        ),
    ]
