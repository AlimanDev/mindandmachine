# Generated by Django 2.0 on 2018-05-17 20:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0016_auto_20180517_1958'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='tabel_code',
            field=models.CharField(blank=True, max_length=15, null=True),
        ),
    ]
