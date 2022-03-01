# Generated by Django 3.2.9 on 2022-02-25 10:18

from django.db import migrations, models
import django.db.models.deletion

def set_network_for_empty_values(apps, schema_editor):
    Network = apps.get_model('base', 'Network')
    network = Network.objects.order_by('id').first()
    models_to_update = [
        'slot', 'worktypename'
    ]

    for model in models_to_update:
        model = apps.get_model('timetable', model)
        model.objects.filter(network_id__isnull=True).update(network=network)

class Migration(migrations.Migration):

    dependencies = [
        ('base', '0170_auto_20220225_1018'),
        ('timetable', '0116_auto_20220217_0741'),
    ]

    operations = [
        migrations.RunPython(set_network_for_empty_values, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='slot',
            name='network',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='base.network'),
        ),
        migrations.AlterField(
            model_name='workerday',
            name='source',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Создание рабочего дня через быстрый редактор'), (1, 'Создание рабочего дня через полный редактор'), (2, 'Создание через копирование в графике (ctrl-c + ctrl-v)'), (3, 'Автоматическое создание алгоритмом'), (4, 'Автоматическое создание биржей смен'), (5, 'Создание смен через change_range (Обычно используется для получения отпусков/больничных из 1С ЗУП)'), (6, 'Создание смен через copy_range (Копирование по датам)'), (7, 'Создание смен через exchange (Обмен сменами)'), (8, 'Создание смен через exchange_approved (Обмен сменами в подтвержденной версии)'), (9, 'Создание смен через загрузку графика'), (10, 'Создание смен через change_list (Проставление типов дней на промежуток для сотрудника)'), (11, 'Автоматическое создание смен через shift_elongation (Расширение смен)'), (12, 'Автоматическое создание смен при отмене вакансии'), (13, 'Автоматическое создание смен при принятии вакансии'), (14, 'Создание смен через интеграцию'), (15, 'Создание смен при подтверждении графика'), (16, 'Создание смен при получении редактируемой вакансии'), (17, 'Создание смен через copy_approved (Копирование из плана в план)'), (18, 'Создание смен через copy_approved (Копирование из плана в факт)'), (19, 'Создание смен через copy_approved (Копирование из факта в факт)'), (20, 'Создание смен во время отметок'), (21, 'Пересчет факта на основе отметок')], default=0, verbose_name='Источник создания'),
        ),
        migrations.AlterField(
            model_name='worktypename',
            name='network',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='base.network'),
        ),
    ]
