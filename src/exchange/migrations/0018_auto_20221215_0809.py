# Generated by Django 3.2.9 on 2022-12-15 08:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0017_auto_20221214_1317'),
    ]

    operations = [
        migrations.AddField(
            model_name='importhistdatastrategy',
            name='remove_duplicates_columns',
            field=models.JSONField(blank=True, null=True, verbose_name='По каким колонкам будем удалять лишние записи для вставки в базу'),
        ),
    ]