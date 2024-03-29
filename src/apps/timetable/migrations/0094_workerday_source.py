# Generated by Django 2.2.16 on 2021-10-22 05:47

from django.db import migrations, models

def set_source(apps, schema_editor):
    WorkerDay = apps.get_model('timetable', 'WorkerDay')
    WorkerDay.objects.filter(
        created_by__isnull=True,
        is_vacancy=False,
    ).update(
        source=3, # algo
    )
    WorkerDay.objects.filter(
        created_by__isnull=True,
        is_vacancy=True,
    ).update(
        source=4, # auto vacancy
    )
    WorkerDay.objects.filter(
        created_by__isnull=False,
        is_vacancy=True,
    ).update(
        source=1, # vacancy
    )


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0093_auto_20211020_1216'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='source',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Создание рабочего дня через быстрый редактор'), (1, 'Создание рабочего дня через полный редактор'), (2, 'Создание через копирование в графике (ctrl-c + ctrl-v)'), (3, 'Автоматическое создание алгоритмом'), (4, 'Автоматическое создание биржей смен'), (5, 'Создание смен через change_range (Обычно используется для получения отпусков/больничных из 1С ЗУП)'), (6, 'Создание смен через copy_range (Копирование по датам)'), (7, 'Создание смен через exchange (Обмен сменами)'), (8, 'Создание смен через exchange_approved (Обмен сменами в подтвержденной версии)'), (9, 'Создание смен через загрузку графика'), (10, 'Создание смен через change_list (Проставление типов дней на промежуток для сотрудника)'), (11, 'Автоматическое создание смен через shift_elongation (Расширение смен)'), (12, 'Автоматическое создание смен при отмене вакансии'), (13, 'Автоматическое создание смен при принятии вакансии'), (14, 'Создание смен через интеграцию'), (15, 'Создание смен при подтверждении графика'), (16, 'Создание смен при получении редактируемой вакансии'), (17, 'Создание смен через copy_approved (Копирование из плана в план)'), (18, 'Создание смен через copy_approved (Копирование из плана в факт)'), (19, 'Создание смен через copy_approved (Копирование из факта в факт)')], default=0, verbose_name='Источник создания'),
        ),
        migrations.RunPython(set_source, migrations.RunPython.noop),
    ]
