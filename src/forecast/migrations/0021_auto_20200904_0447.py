# Generated by Django 2.2.7 on 2020-09-04 04:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0020_merge_20200826_1619'),
    ]

    operations = [
        migrations.AlterField(
            model_name='operationtypename',
            name='name',
            field=models.CharField(max_length=128),
        ),
    ]
