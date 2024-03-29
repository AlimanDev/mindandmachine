# Generated by Django 2.2.16 on 2021-08-18 07:35

from django.db import migrations
from etc.scripts.fill_calendar import fill_days
from datetime import date
from dateutil.relativedelta import relativedelta

def sync_production_day(app, schema_editor):
    dt_from = date.today().replace(month=1, day=1)
    dt_to = dt_from.replace(month=12, day=31) + relativedelta(year=1)
    Region = app.get_model('base', 'Region')
    Region.objects.filter(id=1).update(code='ru', name='Россия')
    fill_days(dt_from.strftime('%Y.%m.%d'), dt_to.strftime('%Y.%m.%d'), region_id=1)

class Migration(migrations.Migration):

    dependencies = [
        ('base', '0116_auto_20210728_1004'),
    ]

    operations = [
        migrations.RunPython(sync_production_day)
    ]
