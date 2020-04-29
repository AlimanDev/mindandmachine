# Generated by Django 2.2.7 on 2020-04-17 10:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0024_auto_20200417_1014'),
        ('forecast', '0008_merge_20200417_1014'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='operationtype',
            unique_together={('shop', 'operation_type_name')},
        ),
        migrations.AlterUniqueTogether(
            name='operationtyperelation',
            unique_together={('base', 'depended')},
        ),
        migrations.AddField(
            model_name='operationtyperelation',
            name='convert_min_to_real',
            field=models.BooleanField(default=False),
        ),
    ]
