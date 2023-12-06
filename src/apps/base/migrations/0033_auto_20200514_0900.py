# Generated by Django 2.2.7 on 2020-05-14 09:00

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0032_auto_20200513_1801'),
    ]

    operations = [
        migrations.AddField(
            model_name='region',
            name='network',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Network'),
        ),
        migrations.AddField(
            model_name='shopsettings',
            name='network',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Network'),
        ),
    ]