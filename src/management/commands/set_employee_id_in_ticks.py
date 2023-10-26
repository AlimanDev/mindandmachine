import datetime

from django.core.management import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Setting employee_id in ticks where are they null'

    def handle(self, *args, **options):
        dt = datetime.datetime.now() - datetime.timedelta(days=180)
        query = f"""with user_empl as (
                        select u.id as uid, max(e.id) as uemp
                        from base_user u join base_employee e on u.id = e.user_id
                        group by u.id  
                    )
                    update public.recognition_tick as rt
                    set rt.employee_id = ue.uemp
                    from user_empl ue
                    where rt.user_id = ue.uid and dttm >= date '{dt}'"""

        with connection.cursor() as cursor:
            cursor.execute(query)

        self.stdout.write(self.style.SUCCESS(f'SUCCESS'))
