# Generated by Django 2.2.16 on 2021-06-07 20:56

from django.db import migrations


def update_prod_cal_view(apps, schema_editor):
    sql = """\
    CREATE OR REPLACE VIEW prod_cal AS
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
       FROM base_employment employment
         JOIN base_shop s ON employment.shop_id = s.id
         JOIN base_region r ON s.region_id = r.id
         JOIN base_productionday pd ON
             (pd.dt >= employment.dt_hired OR employment.dt_hired IS NULL)
             AND (pd.dt <= employment.dt_fired OR employment.dt_fired IS NULL)
             AND (pd.region_id = r.id or pd.region_id = r.parent_id)
                 AND pd.id = (
                     SELECT pd2.id FROM base_productionday pd2 WHERE
                         (pd2.dt >= employment.dt_hired OR employment.dt_hired IS NULL)
                         AND (pd2.dt <= employment.dt_fired OR employment.dt_fired IS NULL)
                         AND (pd2.region_id = r.id or pd2.region_id = r.parent_id)
                         AND pd2.dt = pd.dt
                     ORDER BY pd2.region_id = r.id DESC, pd2.region_id = r.parent_id DESC
                     LIMIT 1
                 )
         JOIN base_employee employee ON employment.employee_id = employee.id
         JOIN base_user u ON employee.user_id = u.id
         LEFT JOIN base_workerposition wp ON employment.position_id = wp.id AND pd.dt >= '2020-01-01'::date
      WHERE employment.dttm_deleted IS NULL
      GROUP BY pd.id, pd.dt, employee.user_id, employment.id, u.username, employment.shop_id, s.code, pd.region_id;
    """
    schema_editor.execute(sql)


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0109_region_parent'),
    ]

    operations = [
        migrations.RunPython(update_prod_cal_view, migrations.RunPython.noop),
    ]
