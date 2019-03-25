from django.db import migrations
from src.db.works.fill_production_calendar import fill_calendar


def fill_days(apps, schema_editor):
    ProductionMonth = apps.get_model('db', 'ProductionMonth')
    ProductionDay = apps.get_model('db', 'ProductionDay')

    ProductionMonth.objects.all().delete()
    ProductionDay.objects.all().delete()

    fill_calendar.main('2016.1.1', '2020.1.1')


class Migration(migrations.Migration):
    dependencies = [
        ('db', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(fill_days)
    ]
