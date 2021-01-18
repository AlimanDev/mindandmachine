# Generated by Django 2.2.7 on 2020-12-15 20:12

from django.conf import settings
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('base', '0071_merge_20201209_1450'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EventType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('dttm_added', models.DateTimeField(default=django.utils.timezone.now)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128, verbose_name='Имя')),
                ('code', models.CharField(max_length=64, verbose_name='Код')),
                ('write_history', models.BooleanField(default=True, verbose_name='Сохранять историю события')),
                ('network', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Network')),
            ],
            options={
                'verbose_name': 'Тип события',
                'verbose_name_plural': 'Типы событий',
                'unique_together': {('code', 'network')},
            },
        ),
        migrations.CreateModel(
            name='EventHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('context', django.contrib.postgres.fields.jsonb.JSONField(default=dict)),
                ('event_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.EventType')),
                ('shop', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='base.Shop')),
                ('user_author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'История события',
                'verbose_name_plural': 'История событий',
            },
        ),
    ]
