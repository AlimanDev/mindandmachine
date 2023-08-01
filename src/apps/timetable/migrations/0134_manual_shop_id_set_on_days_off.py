# Создано вручную 2023-27-06 11:15
# Проставляем всем имеющимся выходным shop_id
from django.core.paginator import Paginator
from django.db import migrations
import datetime


def set_shop_id_on_days_off(apps, schema_editor):
    WorkerDay = apps.get_model('timetable', 'WorkerDay')
    this_year = datetime.datetime(2023, 1, 1)
    wds_qs = WorkerDay.objects.select_related('employment').filter(shop_id__isnull=True,
                                                                   employment__isnull=False,
                                                                   dt__gte=this_year).order_by('id')

    paginator = Paginator(wds_qs, 2000)

    for page_number in paginator.page_range:
        page = paginator.page(page_number)
        updates = []

        for wd in page.object_list:
            wd.shop_id = wd.employment.shop_id
            updates.append(wd)

        WorkerDay.objects.bulk_update(updates, ['shop_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0133_workerday_dt_not_actual'),
    ]

    operations = [
        migrations.RunPython(set_shop_id_on_days_off),
    ]