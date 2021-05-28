# Generated by Django 2.2.16 on 2021-05-28 09:06

from django.db import migrations


def update_prod_cal_view(apps, schema_editor):
    schema_editor.execute(
        """
        create or replace view prod_cal as
        SELECT pd.id,
        pd.dt,
        employee.user_id,
        employment.id AS employment_id,
        u.username,
        employment.shop_id,
        s.code,
        pd.region_id,
        sum(
            CASE
                WHEN pd.type::text = 'W'::text THEN 8::double precision * COALESCE(wp.hours_in_a_week::integer, 40)::double precision / 40::double precision * employment.norm_work_hours::double precision / 100::double precision
                WHEN pd.type::text = 'S'::text THEN 8::double precision * COALESCE(wp.hours_in_a_week::integer, 40)::double precision / 40::double precision * employment.norm_work_hours::double precision / 100::double precision - 1::double precision
                ELSE 0::double precision
            END) AS norm_hours,
        employment.employee_id
       FROM base_productionday pd
         JOIN base_employment employment ON (pd.dt >= employment.dt_hired OR employment.dt_hired IS NULL) AND (pd.dt <= employment.dt_fired OR employment.dt_fired IS NULL) AND employment.dttm_deleted IS NULL
         JOIN base_employee employee ON employment.employee_id = employee.id
         JOIN base_user u ON employee.user_id = u.id
         JOIN base_shop s ON employment.shop_id = s.id AND pd.region_id = s.region_id
         LEFT JOIN base_workerposition wp ON employment.position_id = wp.id AND pd.dt >= '2020-01-01'::date
      GROUP BY pd.id, pd.dt, employee.user_id, employment.id, u.username, employment.shop_id, s.code, pd.region_id;
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0104_auto_20210525_1457'),
    ]

    operations = [
        migrations.RunPython(update_prod_cal_view, migrations.RunPython.noop),
    ]
