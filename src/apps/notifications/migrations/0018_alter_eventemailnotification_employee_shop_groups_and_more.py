# Generated by Django 4.1.7 on 2023-03-09 15:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0194_alter_network_forbid_edit_work_days_came_through_integration_and_more'),
        ('notifications', '0017_auto_20221220_1402'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventemailnotification',
            name='employee_shop_groups',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.group', verbose_name='Оповещать пользователей магазина сотрудника, имеющих выбранные группы'),
        ),
        migrations.AlterField(
            model_name='eventemailnotification',
            name='groups',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.group', verbose_name='Оповещать пользователей определенных групп'),
        ),
        migrations.AlterField(
            model_name='eventemailnotification',
            name='shop_groups',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.group', verbose_name='Оповещать пользователей магазина, имеющих выбранные группы'),
        ),
        migrations.AlterField(
            model_name='eventonlinenotification',
            name='employee_shop_groups',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.group', verbose_name='Оповещать пользователей магазина сотрудника, имеющих выбранные группы'),
        ),
        migrations.AlterField(
            model_name='eventonlinenotification',
            name='groups',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.group', verbose_name='Оповещать пользователей определенных групп'),
        ),
        migrations.AlterField(
            model_name='eventonlinenotification',
            name='shop_groups',
            field=models.ManyToManyField(blank=True, related_name='+', to='base.group', verbose_name='Оповещать пользователей магазина, имеющих выбранные группы'),
        ),
    ]
