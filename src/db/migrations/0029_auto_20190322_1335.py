# Generated by Django 2.0.5 on 2019-03-22 13:35

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0028_remove_shop_full_interface'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='attendancerecords',
            options={'verbose_name': 'Данные УРВ'},
        ),
        migrations.AlterModelOptions(
            name='cameracashbox',
            options={'verbose_name': 'Камеры-кассы'},
        ),
        migrations.AlterModelOptions(
            name='cameracashboxstat',
            options={'verbose_name': 'Статистика по модели камера-касса'},
        ),
        migrations.AlterModelOptions(
            name='emptyoutcomevisitors',
            options={'verbose_name': 'Выходящие без покупок посетители (по периодам)'},
        ),
        migrations.AlterModelOptions(
            name='incomevisitors',
            options={'verbose_name': 'Входящие посетители (по периодам)'},
        ),
        migrations.AlterModelOptions(
            name='notifications',
            options={'verbose_name': 'Уведомления'},
        ),
        migrations.AlterModelOptions(
            name='operationtype',
            options={'verbose_name': 'Тип операции', 'verbose_name_plural': 'Типы операций'},
        ),
        migrations.AlterModelOptions(
            name='periodclients',
            options={'verbose_name': 'Спрос по клиентам'},
        ),
        migrations.AlterModelOptions(
            name='perioddemandchangelog',
            options={'verbose_name': 'Лог изменений спроса'},
        ),
        migrations.AlterModelOptions(
            name='periodproducts',
            options={'verbose_name': 'Спрос по продуктам'},
        ),
        migrations.AlterModelOptions(
            name='periodqueues',
            options={'verbose_name': 'Очереди'},
        ),
        migrations.AlterModelOptions(
            name='productionday',
            options={'verbose_name': 'День производственного календаря'},
        ),
        migrations.AlterModelOptions(
            name='productionmonth',
            options={'ordering': ('dt_first',), 'verbose_name': 'Производственный календарь'},
        ),
        migrations.AlterModelOptions(
            name='purchasesoutcomevisitors',
            options={'verbose_name': 'Выходящие с покупками посетители (по периодам)'},
        ),
        migrations.AlterModelOptions(
            name='region',
            options={'verbose_name': 'Регион', 'verbose_name_plural': 'Регионы'},
        ),
        migrations.AlterModelOptions(
            name='timetable',
            options={'verbose_name': 'Расписание', 'verbose_name_plural': 'Расписания'},
        ),
        migrations.AlterModelOptions(
            name='userweekdayslot',
            options={'verbose_name': 'Пользовательский слот', 'verbose_name_plural': 'Пользовательские слоты'},
        ),
        migrations.AlterModelOptions(
            name='workercashboxinfo',
            options={'verbose_name': 'Информация по сотруднику-типу работ'},
        ),
        migrations.AlterModelOptions(
            name='workerconstraint',
            options={'verbose_name': 'Ограничения сотрудника'},
        ),
        migrations.AlterModelOptions(
            name='workerday',
            options={'verbose_name': 'Рабочий день сотрудника', 'verbose_name_plural': 'Рабочие дни сотрудников'},
        ),
        migrations.AlterModelOptions(
            name='workerdaycashboxdetails',
            options={'verbose_name': 'Детали в течение рабочего дня'},
        ),
        migrations.AlterModelOptions(
            name='workerdaychangerequest',
            options={'verbose_name': 'Запрос на изменения рабочего дня'},
        ),
        migrations.AlterModelOptions(
            name='workermonthstat',
            options={'verbose_name': 'Статистика по рабоче сотрудника за месяц'},
        ),
    ]