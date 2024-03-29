# Generated by Django 2.2.7 on 2019-12-23 10:19

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkTypeName',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_added', models.DateTimeField(default=django.utils.timezone.now)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128)),
                ('code', models.CharField(default='', max_length=64)),
            ],
            options={
                'verbose_name': 'Название типа работ',
                'verbose_name_plural': 'Названия типов работ',
            },
        ),
        migrations.RunSQL('insert into timetable_worktypename (name, dttm_added, code) select distinct name, now(), 0  from timetable_worktype'),
        migrations.RemoveField(
            model_name='cashbox',
            name='number',
        ),
        migrations.AddField(
            model_name='cashbox',
            name='code',
            field=models.CharField(default='', max_length=64),
        ),
        migrations.AddField(
            model_name='cashbox',
            name='name',
            field=models.CharField(default=1, max_length=128),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='slot',
            name='code',
            field=models.CharField(default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='cashbox',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='slot',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='slot',
            name='name',
            field=models.CharField(default=1, max_length=128),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='workerdayapprove',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='worktype',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
