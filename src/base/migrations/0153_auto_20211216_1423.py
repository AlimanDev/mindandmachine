# Generated by Django 3.2.9 on 2021-12-16 14:23

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0152_auto_20211129_1613'),
    ]

    operations = [
        migrations.AddField(
            model_name='shiftscheduleday',
            name='day_hours',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=4, verbose_name='Сумма дневных часов'),
        ),
        migrations.AddField(
            model_name='shiftscheduleday',
            name='night_hours',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=4, verbose_name='Сумма ночных часов'),
        ),
    ]
