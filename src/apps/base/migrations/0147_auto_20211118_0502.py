# Generated by Django 3.2.9 on 2021-11-18 05:02

import json
from django.db import migrations

def update_shop_default_values(apps, schema_editor):
    Network = apps.get_model('base', 'Network')
    for n in Network.objects.all():
        shop_default_values = json.loads(n.shop_default_values)
        if shop_default_values:
            n.shop_default_values = json.dumps(
                {
                    '.*': shop_default_values,
                }
            )
            n.save()

class Migration(migrations.Migration):

    dependencies = [
        ('base', '0146_auto_20211117_1414'),
    ]

    operations = [
        migrations.RunPython(update_shop_default_values, migrations.RunPython.noop),
    ]