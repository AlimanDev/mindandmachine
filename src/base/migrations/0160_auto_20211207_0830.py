# Generated by Django 3.2.9 on 2021-12-07 08:30

import re
from django.db import migrations

def set_group_codes_and_subordinates(apps, schema_editor):
    Group = apps.get_model('base', 'Group')
    codes = [
        (r'админ(истратор)?(?=$|(\sm&m)|(\smm)|(\sмм))', 'admin'),
        (r'админ(истратор)?(?=\sаутсорс)', 'admin_outsource'),
        (r'(?!.*((m&m)|(mm)|(мм)|(аутсорс)).*)(^админ(истратор)? .*$)', 'admin_client'),
        (r'сотрудник', 'worker'),
        (r'(?!.*супервайзер.*)(^.*директор.*$)', 'director'),
        (r'(?!.*((руководитель)|(открывающий)).*)(^.*((урс)|(супервайзер)).*$)', 'urs'),
        (r'.*руководитель урс.*', 'urs_managers'),
    ]
    codes_subordinates = [
        ('admin', ['admin', 'admin_outsource', 'admin_client', 'worker', 'director', 'urs', 'urs_managers']),
        ('admin_outsource', ['admin_outsource', 'worker']),
        ('admin_client', ['admin_client', 'urs', 'director', 'worker']),
        ('director', ['director', 'worker']),
        ('urs', ['urs', 'director', 'worker']),
        ('urs_managers', ['urs_managers', 'urs', 'director', 'worker']),
    ]
    for g in Group.objects.all():
        for pattern, code in codes:
            if re.search(pattern, g.name, re.IGNORECASE):
                g.code = code
                g.save()
                break
    
    for code, subordinates in codes_subordinates:
        group = Group.objects.filter(code=code).first()
        if group:
            group.subordinates.add(*Group.objects.filter(code__in=subordinates))


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0159_auto_20211207_0700'),
    ]

    operations = [
        migrations.RunPython(set_group_codes_and_subordinates, migrations.RunPython.noop)
    ]
