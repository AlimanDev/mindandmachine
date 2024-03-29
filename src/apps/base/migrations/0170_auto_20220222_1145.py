# Generated by Django 3.2.9 on 2022-02-22 11:45

from django.db import migrations


def add_permissions(apps, schema_editor):
    permissions = [
        ('MedicalDocumentType', 'GET', (
            'admin', 'admin_outsource', 'admin_client', 'urs', 'urs_managers', 'controller', 'director', 'worker')),
        ('MedicalDocument', 'GET', (
            'admin', 'admin_outsource', 'admin_client', 'urs', 'urs_managers', 'controller', 'director', 'worker')),
        ('MedicalDocument', 'POST', ('admin', 'admin_outsource', 'admin_client')),
        ('MedicalDocument', 'PUT', ('admin', 'admin_outsource', 'admin_client')),
        ('MedicalDocument', 'DELETE', ('admin', 'admin_outsource', 'admin_client')),
    ]

    Group = apps.get_model('base', 'Group')
    FunctionGroup = apps.get_model('base', 'FunctionGroup')

    for func, method, groups in permissions:
        for group in Group.objects.filter(code__in=groups):
            FunctionGroup.objects.get_or_create(
                group=group,
                method=method,
                func=func,
                defaults=dict(
                    access_type='all',
                )
            )


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0169_auto_20220214_1146'),
    ]

    operations = [
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
