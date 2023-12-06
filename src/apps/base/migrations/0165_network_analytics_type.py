# Generated by Django 3.2.9 on 2022-01-27 23:16

import json

from django.db import migrations, models


def set_analytics_type(apps, schema_editor):
    Network = apps.get_model('base', 'Network')
    for network in Network.objects.all():
        settings_values = json.loads(network.settings_values)
        analytics_iframe = settings_values.get('analytics_iframe')
        if analytics_iframe:
            network.analytics_type = 'custom_iframe'
            network.save(update_fields=['analytics_type'])


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0164_auto_20211223_1107'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='analytics_type',
            field=models.CharField(choices=[('metabase', 'Метабейз'), ('custom_iframe', 'Кастомный iframe (из json настройки analytics_iframe)'), ('power_bi_embed', 'Power BI через получение embed токена')], default='metabase', max_length=32),
        ),
        migrations.RunPython(
            set_analytics_type, migrations.RunPython.noop,
        )
    ]