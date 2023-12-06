# Generated by Django 3.2.9 on 2022-02-15 23:43

from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0169_auto_20220214_1146'),
        ('reports', '0012_auto_20220210_0028'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmploymentStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dt', models.DateField()),
                ('sawh_hours', models.DecimalField(decimal_places=14, default=Decimal('0'), max_digits=16)),
                ('reduce_norm', models.BooleanField()),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='base.employee')),
                ('employment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='base.employment')),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='base.shop')),
            ],
        ),
    ]