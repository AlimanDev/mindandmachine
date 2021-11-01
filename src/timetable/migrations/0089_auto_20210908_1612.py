# Generated by Django 2.2.16 on 2021-09-08 16:12

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0088_auto_20210906_1553'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerday',
            name='parent_worker_day',
            field=models.ForeignKey(blank=True, help_text='Используется в подтверждении рабочих дней для того, чтобы понимать каким днем из подтв. версии был порожден день в черновике, чтобы можно было сопоставить и создать детали рабочего дня', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='child', to='timetable.WorkerDay'),
        ),
        migrations.AlterField(
            model_name='workerdaychangerequest',
            name='type',
            field=models.CharField(choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('E', 'Пусто'), ('TV', 'Отпуск за свой счёт')], default='E', max_length=2),
        ),
        migrations.AlterField(
            model_name='workerdaypermission',
            name='wd_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='timetable.WorkerDayType', verbose_name='Тип дня'),
        ),
    ]