# Generated by Django 2.2.16 on 2021-08-30 09:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0119_network_shop_default_values'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='add_users_from_excel',
            field=models.BooleanField(default=False, verbose_name='Upload employments from excel'),
        ),
    ]