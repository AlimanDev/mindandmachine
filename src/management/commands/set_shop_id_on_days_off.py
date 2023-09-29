from django.core.management import BaseCommand
from django.db import connection

query = """
with data_emp as (
    select 
        w.id as wid,
	    e.id as eid,
	    e.shop_id as eshop
    from 
        public.timetable_workerday w
    join 
        public.timetable_workerdaytype wt ON w.type_id = wt.code and wt.is_dayoff = true
    join
        base_employment e ON w.employment_id = e.id
    where 
        w.dt >= date '2023-01-01'
    and 
        w.shop_id is null
)
update 
    public.timetable_workerday AS ww
set 
    shop_id = d.eshop
from 
    data_emp AS d
where 
    ww.id = d.wid
"""


class Command(BaseCommand):
    help = "Sets the shop_id for the worker_day based on the shop from the associated user's employment"

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(query)

        self.stdout.write(self.style.SUCCESS(f'SUCCESS'))
