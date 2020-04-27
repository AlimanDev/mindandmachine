# Generated by Django 2.2.7 on 2020-04-27 10:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0023_auto_20200427_1045'),
        ('forecast', '0008_operationtypename_is_special'),
    ]

    operations = [
        migrations.AddField(
            model_name='operationtype',
            name='shop',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='operation_types', to='base.Shop'),
        ),
    ]
