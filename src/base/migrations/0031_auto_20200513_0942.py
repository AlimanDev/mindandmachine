# Generated by Django 2.2.7 on 2020-05-13 09:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0030_auto_20200513_0851'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='primary_color',
            field=models.CharField(blank=True, max_length=6),
        ),
        migrations.AddField(
            model_name='network',
            name='secondary_color',
            field=models.CharField(blank=True, max_length=6),
        ),
    ]
