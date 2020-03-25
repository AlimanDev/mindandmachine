# Generated by Django 2.2.7 on 2019-12-23 10:19

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='shop',
            old_name='title',
            new_name='name',
        ),
        migrations.RenameField(
            model_name='workerposition',
            old_name='title',
            new_name='name',
        ),
        migrations.AddField(
            model_name='group',
            name='code',
            field=models.CharField(default='', max_length=64),
        ),
        migrations.AddField(
            model_name='group',
            name='dttm_deleted',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='region',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='region',
            name='dttm_deleted',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workerposition',
            name='code',
            field=models.CharField(default='', max_length=64),
        ),
        migrations.AddField(
            model_name='workerposition',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='workerposition',
            name='dttm_deleted',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='employment',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='group',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='region',
            name='code',
            field=models.CharField(default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='region',
            name='name',
            field=models.CharField(max_length=128),
        ),
        migrations.AlterField(
            model_name='shop',
            name='code',
            field=models.CharField(default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='shop',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]