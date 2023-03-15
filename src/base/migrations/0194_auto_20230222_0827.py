# Generated by Django 3.2.9 on 2023-02-22 08:27

from django.db import migrations, models


def blank_to_null(apps, schema_editor):
    Employee = apps.get_model('base', 'Employee')
    Employee.objects.filter(tabel_code='').update(tabel_code=None)


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0193_merge_20230118_1255'),
    ]

    operations = [
        migrations.RunPython(blank_to_null),
        migrations.AlterField(
            model_name='employee',
            name='tabel_code',
            field=models.CharField(default=None, max_length=64, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='network',
            name='forbid_edit_work_days_came_through_integration',
            field=models.BooleanField(blank=True, default=False, null=True, verbose_name='Forbid editing work days which came from integration'),
        ),
        migrations.AlterUniqueTogether(
            name='employee',
            unique_together=set(),
        ),
    ]
