from django.db import migrations
import pandas as pd

from src.conf.djconfig import QOS_DATE_FORMAT


# def fill_days(apps, schema_editor):
#     # We can't import the Person model directly as it may be a newer
#     # version than this migration expects. We use the historical version.
#     ProductionMonth = apps.get_model('db', 'ProductionMonth')
#     ProductionDay = apps.get_model('db', 'ProductionDay')
#
#     # months 2018 creating
#     months = pd.read_csv(
#         'src/db/works/months_2019.csv',
#         index_col=False,
#         sep=';',
#         names=['months', 'days', 'workdays', 'workhours'],
#     )
#
#     months['months'] = pd.to_datetime(months['months'], format=QOS_DATE_FORMAT)
#     for row in months.iterrows():
#         el = row[1]
#         ProductionMonth.objects.get_or_create(
#             dt_first=el['months'].date(),
#             total_days=el['days'],
#             norm_work_days=el['workdays'],
#             norm_work_hours=el['workhours'],
#         )
#
#     days = pd.read_csv(
#         'src/db/works/days_2019.csv',
#         index_col=False,
#         sep=';',
#         names=['dts', 'types']
#     )
#
#     days['dts'] = pd.to_datetime(days['dts'], format=QOS_DATE_FORMAT)
#     for row in days.iterrows():
#         el = row[1]
#         ProductionDay.objects.get_or_create(
#             dt=el['dts'].date(),
#             type=el['types'],
#         )


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0003_auto_20181118_1933'),
    ]

    operations = [
        # actually 0002_fill_production_days_months.py do the same work
    ]