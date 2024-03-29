# Generated by Django 3.2.9 on 2021-11-24 13:16

from django.db import migrations, models
from django.conf import settings

def set_trust_tick_request(apps, schema_editor):
    trust_tick_request = getattr(settings, 'TRUST_TICK_REQUEST', False)
    Network = apps.get_model('base', 'Network')
    Network.objects.update(trust_tick_request=trust_tick_request)


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0151_merge_20211122_1104'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='trust_tick_request',
            field=models.BooleanField(default=False, verbose_name='Create attendance record without check photo.'),
        ),
        migrations.RunPython(set_trust_tick_request, migrations.RunPython.noop),
    ]
