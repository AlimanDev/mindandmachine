# Generated by Django 2.2.16 on 2021-05-20 19:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integration', '0003_auto_20210518_2152'),
    ]

    operations = [
        migrations.CreateModel(
            name='VMdaUsers',
            fields=[
                ('code', models.TextField(primary_key=True, serialize=False)),
                ('username', models.TextField()),
                ('last_name', models.TextField()),
                ('first_name', models.TextField()),
                ('middle_name', models.TextField()),
                ('email', models.TextField()),
                ('dt_hired', models.DateField()),
                ('dt_fired', models.DateField()),
                ('active', models.BooleanField()),
                ('level', models.TextField()),
                ('role', models.TextField()),
                ('shop_name', models.TextField()),
                ('shop_code', models.TextField()),
                ('position_name', models.TextField()),
                ('position_code', models.TextField()),
                ('position_group_name', models.TextField()),
                ('position_group_code', models.TextField()),
                ('func_group_name', models.TextField()),
                ('func_group_code', models.TextField()),
                ('user_last_modified', models.DateTimeField()),
                ('employment_last_modified', models.DateTimeField()),
                ('position_last_modified', models.DateTimeField()),
                ('last_modified', models.DateTimeField()),
            ],
            options={
                'db_table': 'v_mda_users',
                'managed': False,
            },
        ),
    ]