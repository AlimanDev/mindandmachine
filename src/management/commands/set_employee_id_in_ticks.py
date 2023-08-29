import datetime

from django.core.management import BaseCommand

from src.apps.base.models import Employee
from src.apps.recognition.models import Tick


class Command(BaseCommand):
    help = 'Setting employee_id in ticks where are they null'

    def handle(self, *args, **options):
        dt = datetime.datetime.now() - datetime.timedelta(days=180)
        ticks = list(Tick.objects.filter(dttm_added__gte=dt, employee_id__isnull=True))
        updates = []
        for tick in ticks:
            employee = Employee.objects.filter(user_id=tick.user_id).order_by('-id').first()
            tick.employee_id = employee.id
            updates.append(tick)

        Tick.objects.bulk_update(updates, ['employee_id'])
