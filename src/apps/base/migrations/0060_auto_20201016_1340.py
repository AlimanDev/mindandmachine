# Generated by Django 2.2.7 on 2020-10-16 13:40

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Subquery, OuterRef


def set_empl_network(apps, schema_editor):
    Employment = apps.get_model('base', 'Employment')
    User = apps.get_model('base', 'User')
    Employment.objects.filter(user__isnull=False, user__network__isnull=False).update(
        network=Subquery(User.objects.filter(id=OuterRef('user_id')).values('network_id')[:1])
    )


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0059_auto_20201012_0620'),
    ]

    operations = [
        migrations.AddField(
            model_name='employment',
            name='code',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name='employment',
            name='network',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Network'),
        ),
        migrations.AlterUniqueTogether(
            name='employment',
            unique_together={('code', 'network')},
        ),
        migrations.RunPython(set_empl_network, migrations.RunPython.noop),
    ]
