# Generated by Django 3.2.9 on 2022-02-21 15:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0169_auto_20220214_1146'),
    ]

    operations = [
        migrations.AddField(
            model_name='sawhsettingsmapping',
            name='employees',
            field=models.ManyToManyField(blank=True, related_name='_base_sawhsettingsmapping_employees_+', to='base.Employee'),
        ),
    ]
