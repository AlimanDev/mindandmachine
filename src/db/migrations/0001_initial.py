# Generated by Django 2.0.3 on 2018-04-18 18:25

from django.conf import settings
import django.contrib.auth.models
import django.contrib.auth.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import src.db.models
import src.db.utils


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0009_alter_user_last_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=30, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('work_type', src.db.utils.EnumField(blank=True, null=True, to_enum=src.db.models.User.WorkType)),
                ('permissions', models.BigIntegerField(default=0)),
                ('middle_name', models.CharField(blank=True, max_length=64, null=True)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('dt_hired', models.DateField(blank=True, null=True)),
                ('dt_fired', models.DateField(blank=True, null=True)),
                ('birthday', models.DateField(blank=True, null=True)),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='user_avatar/%Y/%m')),
                ('comment', models.CharField(default='', max_length=2048)),
                ('auto_timetable', models.BooleanField(default=True)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups')),
            ],
            options={
                'abstract': False,
                'verbose_name_plural': 'users',
                'verbose_name': 'user',
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='Cashbox',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('number', models.CharField(max_length=6)),
                ('bio', models.CharField(default='', max_length=512)),
            ],
        ),
        migrations.CreateModel(
            name='CashboxType',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128)),
                ('speed_coef', models.FloatField(default=1)),
                ('is_stable', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='LevelType',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('type', src.db.utils.EnumField(to_enum=src.db.models.LevelType.Type)),
                ('weekday', models.PositiveSmallIntegerField()),
                ('tm_from', models.TimeField()),
                ('tm_to', models.TimeField()),
            ],
        ),
        migrations.CreateModel(
            name='Notifications',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('text', models.CharField(max_length=512)),
                ('type', src.db.utils.EnumField(to_enum=src.db.models.Notifications.Type)),
                ('shown', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='OfficialHolidays',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('country', models.CharField(max_length=4)),
                ('date', models.DateField()),
            ],
        ),
        migrations.CreateModel(
            name='PeriodDemand',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_forecast', models.DateTimeField()),
                ('clients', models.FloatField()),
                ('products', models.FloatField()),
                ('type', src.db.utils.EnumField(to_enum=src.db.models.PeriodDemand.Type)),
                ('queue_wait_time', models.FloatField()),
                ('queue_wait_length', models.FloatField()),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
        ),
        migrations.CreateModel(
            name='PeriodDemandChangeLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_from', models.DateTimeField()),
                ('dttm_to', models.DateTimeField()),
                ('multiply_coef', models.FloatField(blank=True, null=True)),
                ('set_value', models.FloatField(blank=True, null=True)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
        ),
        migrations.CreateModel(
            name='Shop',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('full_interface', models.BooleanField(default=True)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('title', models.CharField(max_length=64)),
                ('hidden_title', models.CharField(max_length=64)),
                ('mean_queue_length', models.FloatField(default=3)),
                ('max_queue_length', models.FloatField(default=7)),
                ('dead_time_part', models.FloatField(default=0.1)),
                ('beta', models.FloatField(default=0.9)),
                ('demand_coef', models.FloatField(default=1)),
            ],
        ),
        migrations.CreateModel(
            name='SuperShop',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=64, unique=True)),
                ('hidden_title', models.CharField(max_length=64, unique=True)),
                ('code', models.CharField(blank=True, max_length=64, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Timetable',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dt', models.DateField()),
                ('status', src.db.utils.EnumField(to_enum=src.db.models.Timetable.Status)),
                ('dttm_status_change', models.DateTimeField()),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.Shop')),
            ],
        ),
        migrations.CreateModel(
            name='WaitTimeInfo',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dt', models.DateField()),
                ('wait_time', models.PositiveIntegerField()),
                ('proportion', models.FloatField()),
                ('type', src.db.utils.EnumField(to_enum=src.db.models.PeriodDemand.Type)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
        ),
        migrations.CreateModel(
            name='WorkerCashboxInfo',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('period', models.PositiveIntegerField(default=90)),
                ('mean_speed', models.FloatField(default=1)),
                ('bills_amount', models.PositiveIntegerField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='WorkerConstraint',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('weekday', models.SmallIntegerField()),
                ('tm', models.TimeField()),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='WorkerDay',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dt', models.DateField()),
                ('type', src.db.utils.EnumField(to_enum=src.db.models.WorkerDay.Type)),
                ('tm_work_start', models.TimeField(blank=True, null=True)),
                ('tm_work_end', models.TimeField(blank=True, null=True)),
                ('tm_break_start', models.TimeField(blank=True, null=True)),
                ('is_manual_tuning', models.BooleanField(default=False)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('worker_shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='db.Shop')),
            ],
        ),
        migrations.CreateModel(
            name='WorkerDayCashboxDetails',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('tm_from', models.TimeField()),
                ('tm_to', models.TimeField()),
                ('on_cashbox', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.Cashbox')),
                ('worker_day', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDay')),
            ],
        ),
        migrations.CreateModel(
            name='WorkerDayChangeLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_changed', models.DateTimeField(auto_now_add=True)),
                ('worker_day_dt', models.DateField()),
                ('from_type', src.db.utils.EnumField(to_enum=src.db.models.WorkerDay.Type)),
                ('from_tm_work_start', models.TimeField(blank=True, null=True)),
                ('from_tm_work_end', models.TimeField(blank=True, null=True)),
                ('from_tm_break_start', models.TimeField(blank=True, null=True)),
                ('to_type', src.db.utils.EnumField(to_enum=src.db.models.WorkerDay.Type)),
                ('to_tm_work_start', models.TimeField(blank=True, null=True)),
                ('to_tm_work_end', models.TimeField(blank=True, null=True)),
                ('to_tm_break_start', models.TimeField(blank=True, null=True)),
                ('changed_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('worker_day', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDay')),
                ('worker_day_worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='WorkerDayChangeRequest',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('worker_day_dt', models.DateField()),
                ('type', src.db.utils.EnumField(to_enum=src.db.models.WorkerDay.Type)),
                ('tm_work_start', models.TimeField(blank=True, null=True)),
                ('tm_work_end', models.TimeField(blank=True, null=True)),
                ('tm_break_start', models.TimeField(blank=True, null=True)),
                ('worker_day', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDay')),
                ('worker_day_worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='shop',
            name='super_shop',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.SuperShop'),
        ),
        migrations.AddField(
            model_name='notifications',
            name='period_demand_log',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.PeriodDemandChangeLog'),
        ),
        migrations.AddField(
            model_name='notifications',
            name='to_worker',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='notifications',
            name='worker_day_change_log',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDayChangeLog'),
        ),
        migrations.AddField(
            model_name='notifications',
            name='worker_day_change_request',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDayChangeRequest'),
        ),
        migrations.AddField(
            model_name='leveltype',
            name='shop',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.Shop'),
        ),
        migrations.AddField(
            model_name='cashboxtype',
            name='shop',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.Shop'),
        ),
        migrations.AddField(
            model_name='cashbox',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType'),
        ),
        migrations.AddField(
            model_name='user',
            name='shop',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Shop'),
        ),
        migrations.AddField(
            model_name='user',
            name='user_permissions',
            field=models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.Permission', verbose_name='user permissions'),
        ),
        migrations.AlterUniqueTogether(
            name='workerday',
            unique_together={('worker', 'dt')},
        ),
        migrations.AlterUniqueTogether(
            name='workerconstraint',
            unique_together={('worker', 'weekday', 'tm')},
        ),
        migrations.AlterUniqueTogether(
            name='workercashboxinfo',
            unique_together={('worker', 'cashbox_type')},
        ),
        migrations.AlterUniqueTogether(
            name='timetable',
            unique_together={('shop', 'dt')},
        ),
        migrations.AlterUniqueTogether(
            name='shop',
            unique_together={('super_shop', 'title'), ('super_shop', 'hidden_title')},
        ),
    ]
