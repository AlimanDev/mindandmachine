# Generated by Django 2.2.7 on 2020-03-17 12:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0011_user_tabel_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='employment',
            name='is_visible',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='tabel_code',
            field=models.CharField(blank=True, max_length=15, null=True, unique=True),
        ),
    ]
