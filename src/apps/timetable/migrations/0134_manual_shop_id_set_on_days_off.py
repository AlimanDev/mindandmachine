# Создано вручную 2023-27-06 11:15
# Проставляем всем имеющимся выходным shop_id

from django.db import migrations


def set_shop_id_on_days_off(apps, schema_editor):
    WorkerDay = apps.get_model('timetable', 'WorkerDay')
    wds = WorkerDay.objects.select_related('employment').filter(shop_id__isnull=True, employment__isnull=False)

    for wd in wds:
        wd.shop_id = wd.employment.shop_id
        wd.save(update_fields=['shop_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0133_workerday_dt_not_actual'),
    ]

    operations = [
        migrations.RunPython(set_shop_id_on_days_off),
    ]