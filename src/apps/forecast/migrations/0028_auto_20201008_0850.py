# Generated by Django 2.2.7 on 2020-10-08 08:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0027_merge_20200925_0456'),
    ]

    operations = [
        migrations.AddField(
            model_name='loadtemplate',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='operationtemplate',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='operationtype',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='operationtypename',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='operationtyperelation',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='operationtypetemplate',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='periodclients',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='perioddemandchangelog',
            name='dttm_modified',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
