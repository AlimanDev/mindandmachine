# Generated by Django 2.0.5 on 2019-10-30 14:36

import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F


def forwards_func(apps, schema_editor):
    # We get the model from the versioned app registry;
    # if we directly import it, it'll be the wrong version

    User = apps.get_model("db", "User")
    Employment = apps.get_model("db", "Employment")
    Notifications = apps.get_model("db", "Notifications")
    WorkerConstraint = apps.get_model("db", "WorkerConstraint")
    WorkerDay = apps.get_model("db", "WorkerDay")

    db_alias = schema_editor.connection.alias
    array=[]
    for user in User.objects.using(db_alias).all():
        array.append(
        Employment(
            user=user,
            shop=user.shop,
            function_group=user.function_group,
            position=user.position,
            is_fixed_hours=user.is_fixed_hours,
            dt_hired=user.dt_hired,
            dt_fired=user.dt_fired,
            salary=user.salary,
            week_availability=user.week_availability,
            norm_work_hours=user.norm_work_hours,
            shift_hours_length_min=user.shift_hours_length_min,
            shift_hours_length_max=user.shift_hours_length_max,
            min_time_btw_shifts=user.min_time_btw_shifts,
            auto_timetable=user.auto_timetable,
            tabel_code=user.tabel_code,
            is_ready_for_overworkings=user.is_ready_for_overworkings,
            dt_new_week_availability_from=user.dt_new_week_availability_from,
        ))
        if len(array) >= 1000:
            Employment.objects.using(db_alias).bulk_create(
                array
            )
            array=[]

    Employment.objects.using(db_alias).bulk_create(
        array
    )
    array = []

    # for o in Notifications.objects.using(db_alias).all():
    #     o.shop=o.to_worker.shop
    #     o.save()
        # array.append(o)
    #     if len(array) >= 1000:
    #         Notifications.objects.using(db_alias).bulk_update(
    #             array, ['shop']
    #         )
    #         array=[]
    #
    # Notifications.objects.using(db_alias).bulk_update(
    #     array, ['shop']
    # )
    # array = []

    # for o in WorkerConstraint.objects.using(db_alias).all():
    #     o.shop=o.worker.shop
    #     o.save()
    #     array.append(o)
    #
    #     if len(array) >= 1000:
    #         WorkerConstraint.objects.using(db_alias).bulk_update(
    #             array, ['shop']
    #         )
    #         array = []
    #
    # WorkerConstraint.objects.using(db_alias).bulk_update(
    #     array, ['shop']
    # )

    # array = []
    # for o in WorkerDay.objects.using(db_alias).all():
    #     o.shop=o.worker.shop
    #     o.save()
    #     array.append(o)
    #     if len(array) >= 1000:
    #         WorkerDay.objects.using(db_alias).bulk_update(
    #             array, ['shop']
    #         )
    #         array=[]
    #
    # WorkerDay.objects.using(db_alias).bulk_update(
    #     array, ['shop']
    # )
    # array=[]

class Migration(migrations.Migration):

    dependencies = [
        ('db', '0058_auto_20191028_0803'),
    ]

    operations = [
        migrations.CreateModel(
            name='Employment',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('is_fixed_hours', models.BooleanField(default=False)),
                ('attachment_group', models.CharField(choices=[('S', 'staff'), ('O', 'outsource')], default='S', max_length=1)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('dt_hired', models.DateField(default=datetime.date(2019, 1, 1))),
                ('dt_fired', models.DateField(blank=True, null=True)),
                ('salary', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('week_availability', models.SmallIntegerField(default=7)),
                ('norm_work_hours', models.SmallIntegerField(default=100)),
                ('shift_hours_length_min', models.SmallIntegerField(blank=True, null=True)),
                ('shift_hours_length_max', models.SmallIntegerField(blank=True, null=True)),
                ('min_time_btw_shifts', models.SmallIntegerField(blank=True, null=True)),
                ('auto_timetable', models.BooleanField(default=True)),
                ('tabel_code', models.CharField(blank=True, max_length=15, null=True)),
                ('is_ready_for_overworkings', models.BooleanField(default=False)),
                ('dt_new_week_availability_from', models.DateField(blank=True, null=True)),
                ('function_group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Group')),
                ('position', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.WorkerPosition')),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_query_name='employment', to='db.Shop')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_query_name='employment', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Трудоустройство',
                'verbose_name_plural': 'Трудоустройства',

            },
        ),
        migrations.AddField(
            model_name='notifications',
            name='shop',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='notifications', to='db.Shop'),
        ),
        migrations.AddField(
            model_name='workerconstraint',
            name='shop',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='worker_constraints', to='db.Shop'),
        ),
        migrations.AddField(
            model_name='workerday',
            name='shop',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Shop'),
        ),
        migrations.AddField(
            model_name='workerday',
            name='employment',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Employment'),
        ),
        migrations.RunPython(forwards_func),
        migrations.RunSQL([
            "update  db_workerconstraint as w set shop_id=u.shop_id from  db_user u where w.worker_id=u.id",
            "update  db_workerday as w set shop_id=e.shop_id, employment_id=e.id from db_employment e where w.worker_id=e.user_id",
            "update  db_notifications as n set shop_id=u.shop_id from  db_user u where n.to_worker_id=u.id",
        ])
    ]
