# Generated by Django 2.2.7 on 2020-10-06 06:09

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def create_break(apps, schema_editor):
    Break = apps.get_model('base', 'Break')
    Network = apps.get_model('base', 'Network')
    Break.objects.create(
        name='По умолчанию',
        network=Network.objects.first(),
        value='[[0, 360, [30]], [360, 540, [30, 30]], [540, 780, [30, 30, 15]]]',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0056_auto_20201003_1307'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='shopsettings',
            name='break_triplets',
        ),
        migrations.CreateModel(
            name='Break',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_added', models.DateTimeField(default=django.utils.timezone.now)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128)),
                ('code', models.CharField(blank=True, max_length=64, null=True)),
                ('value', models.CharField(default='[]', max_length=1024)),
                ('network', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Network')),
            ],
            options={
                'verbose_name': 'Перерыв',
                'verbose_name_plural': 'Перерывы',
                'abstract': False,
                'unique_together': {('code', 'network')},
            },
        ),
        migrations.RunPython(create_break),
        migrations.AddField(
            model_name='shopsettings',
            name='breaks',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, to='base.Break'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='workerposition',
            name='breaks',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Break'),
        ),
    ]
