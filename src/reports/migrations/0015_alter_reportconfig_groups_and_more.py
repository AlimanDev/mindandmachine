# Generated by Django 4.1.7 on 2023-03-09 15:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # ('base', '0194_alter_network_forbid_edit_work_days_came_through_integration_and_more'),
        ('reports', '0014_alter_reporttype_network'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reportconfig',
            name='groups',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.group', verbose_name='Оповещать пользователей определенных групп'),
        ),
        migrations.AlterField(
            model_name='reportconfig',
            name='shops_to_notify',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.shop', verbose_name='Оповещать по почте магазина'),
        ),
    ]