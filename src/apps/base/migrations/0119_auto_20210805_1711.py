# Generated by Django 2.2.16 on 2021-08-05 17:11

from django.db import migrations


def set_client_specific_network_settings(apps, schema_editor):
    Network = apps.get_model('base', 'Network')
    Network.objects.filter(name__in=['Ортека', 'Монастырев']).update(skip_leaving_tick=True)


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0118_auto_20210805_1628'),
    ]

    operations = [
        migrations.RunPython(set_client_specific_network_settings, migrations.RunPython.noop)
    ]
