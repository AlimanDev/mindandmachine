# Generated by Django 3.2.9 on 2021-11-22 05:44

import re
from django.db import migrations

def set_subordinates(apps, schema_editor):
    Group = apps.get_model('base', 'Group')
    pattern = r'админ(истратор)?(?=$|(\sm&m))'
    groups = list(Group.objects.all())
    for g in groups:
        if re.search(pattern, g.name, re.IGNORECASE):
            g.subordinates.add(*groups)


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0146_auto_20211117_1414'),
    ]

    operations = [
        migrations.RunPython(set_subordinates, migrations.RunPython.noop)
    ]