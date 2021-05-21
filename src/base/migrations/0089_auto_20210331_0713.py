# Generated by Django 2.2.16 on 2021-03-31 07:13

from django.db import migrations

def create_or_replace_metabase_views(app, schema_editor):
    schema_editor.execute(
        """
        CREATE OR REPLACE VIEW public.shop_stats AS
        SELECT shop.id AS shop_id,
            shop.name AS shop_name,
            shop.code AS shop_code,
            shop_stat.is_approved,
            shop_stat.status,
            shop_stat.dt,
            shop_stat.fot AS summary_working_hours_plan,
            shop_stat.idle AS deadtime,
            shop_stat.lack AS covering
        FROM (public.timetable_shopmonthstat shop_stat
            JOIN public.base_shop shop ON shop.id = shop_stat.shop_id)
        ORDER BY shop_stat.dt, shop.name;
        """
    )

class Migration(migrations.Migration):

    dependencies = [
        ('base', '0088_auto_20210330_1140'),
        ('timetable', '0033_shopmonthstat_is_approved'),
    ]

    operations = [
        migrations.RunPython(create_or_replace_metabase_views),
    ]
