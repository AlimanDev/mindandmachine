# Generated by Django 2.2.16 on 2021-04-21 14:31

from django.db import migrations
from django.db.models import Subquery, OuterRef, Q


def fill_employee(apps, schema_editor):
    Employment = apps.get_model('base', 'Employment')
    Employee = apps.get_model('base', 'Employee')
    Employee.objects.bulk_create([Employee(user_id=e['user_id'], tabel_code=e['tabel_code']) for e in
                                  Employment.objects.values('user_id', 'tabel_code').distinct()])
    Employment.objects.all().update(
        employee=Subquery(
            Employee.objects.filter(
                Q(tabel_code__isnull=True) | Q(tabel_code=OuterRef('tabel_code')),
                user_id=OuterRef('user_id'),
            ).values('id')[:1])
    )


def update_views(apps, schema_editor):
    schema_editor.execute(
        """
        create or replace view prod_cal as
        SELECT pd.id,
               pd.dt,
               employee.user_id,
               employment.id as employment_id,
               u.username,
               employment.shop_id,
               s.code,
               pd.region_id,
               sum(
                   CASE
                       WHEN pd.type::text = 'W'::text THEN 8::double precision ::double precision * COALESCE(wp.hours_in_a_week::integer, 40)::double precision /
                   40::double precision * employment.norm_work_hours::double precision /
                   100::double precision
                       WHEN pd.type::text = 'S'::text THEN 8::double precision ::double precision * COALESCE(wp.hours_in_a_week::integer, 40)::double precision /
                   40::double precision * employment.norm_work_hours::double precision /
                   100::double precision - 1::double precision
                       ELSE 0::double precision
                       END
               ) AS norm_hours,
               employment.employee_id
        FROM base_productionday pd
                 JOIN base_employment employment
                      ON (pd.dt >= employment.dt_hired or employment.dt_hired is NULL) AND (pd.dt <= employment.dt_fired or employment.dt_fired is NULL)
                 JOIN base_employee employee on employment.employee_id = employee.id
                 JOIN base_user u ON employee.user_id = u.id
                 JOIN base_shop s ON employment.shop_id = s.id and pd.region_id = s.region_id
                 LEFT JOIN base_workerposition wp ON employment.position_id = wp.id
          and pd.dt >= '2020-01-01'
        GROUP BY pd.id, pd.dt, employee.user_id, employment.id, u.username, employment.shop_id, s.code, pd.region_id;
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0091_auto_20210421_1314'),
        ('timetable', '0061_auto_20210421_1314'),
    ]

    operations = [
        migrations.RunPython(fill_employee, migrations.RunPython.noop),
        migrations.RunPython(update_views, migrations.RunPython.noop),
    ]