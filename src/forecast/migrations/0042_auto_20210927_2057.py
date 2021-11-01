# Generated by Django 2.2.24 on 2021-09-27 20:57

from django.db import migrations, models


def fill_receipt_dt(apps, schema_editor):
    Receipt = apps.get_model('forecast', 'Receipt')
    Receipt.objects.update(dt=models.Subquery(
        Receipt.objects.filter(id=models.OuterRef('id')).values_list('dttm__date')[:1])
    )


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0124_auto_20210927_0952'),
        ('forecast', '0041_auto_20210927_1913'),
    ]

    operations = [
        migrations.AddField(
            model_name='receipt',
            name='dt',
            field=models.DateField(blank=True, null=True, verbose_name='Дата события'),
        ),
        migrations.RunPython(fill_receipt_dt, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='receipt',
            name='dt',
            field=models.DateField(verbose_name='Дата события'),
        ),
        migrations.AlterIndexTogether(
            name='receipt',
            index_together={('dt', 'data_type', 'shop')},
        ),
    ]