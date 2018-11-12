# Generated by Django 2.0.5 on 2018-11-12 08:20

import datetime
from django.conf import settings
import django.contrib.auth.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import src.db.models
import src.db.utils


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
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
                ('is_fixed_hours', models.BooleanField(default=False)),
                ('is_fixed_days', models.BooleanField(default=False)),
                ('group', models.CharField(choices=[('C', 'cashiers'), ('M', 'manager'), ('S', 'supervisor'), ('D', 'director'), ('H', 'headquarter')], default='C', max_length=1)),
                ('attachment_group', models.CharField(choices=[('S', 'staff'), ('O', 'outsource')], default='S', max_length=1)),
                ('middle_name', models.CharField(blank=True, max_length=64, null=True)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('dt_hired', models.DateField(blank=True, null=True)),
                ('dt_fired', models.DateField(blank=True, null=True)),
                ('birthday', models.DateField(blank=True, null=True)),
                ('sex', models.CharField(choices=[('F', 'Female'), ('M', 'Male')], default='F', max_length=1)),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='user_avatar/%Y/%m')),
                ('comment', models.CharField(blank=True, default='', max_length=2048)),
                ('extra_info', models.CharField(blank=True, default='', max_length=512)),
                ('auto_timetable', models.BooleanField(default=True)),
                ('tabel_code', models.CharField(blank=True, max_length=15, null=True)),
                ('phone_number', models.CharField(blank=True, max_length=32, null=True)),
                ('is_ready_for_overworkings', models.BooleanField(default=False)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups')),
            ],
            options={
                'verbose_name': 'Пользователь',
                'verbose_name_plural': 'Пользователи',
            },
            managers=[
                ('objects', src.db.models.WorkerManager()),
            ],
        ),
        migrations.CreateModel(
            name='CameraCashbox',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name='CameraCashboxStat',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm', models.DateTimeField()),
                ('queue', models.FloatField()),
                ('camera_cashbox', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CameraCashbox')),
            ],
        ),
        migrations.CreateModel(
            name='Cashbox',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('number', models.PositiveIntegerField(blank=True, null=True)),
                ('bio', models.CharField(blank=True, default='', max_length=512)),
            ],
            options={
                'verbose_name': 'Касса',
                'verbose_name_plural': 'Кассы',
            },
        ),
        migrations.CreateModel(
            name='CashboxType',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('priority', models.PositiveIntegerField(default=100)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('dttm_last_update_queue', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128)),
                ('speed_coef', models.FloatField(default=1)),
                ('is_stable', models.BooleanField(default=False)),
                ('do_forecast', models.CharField(choices=[('H', 'Hard'), ('L', 'Lite'), ('N', 'None')], default='L', max_length=1)),
                ('probability', models.FloatField(default=1.0)),
                ('prior_weight', models.FloatField(default=1.0)),
                ('is_main_type', models.BooleanField(default=False)),
                ('period_demand_params', models.CharField(default='{"max_depth":-1,"eta":-1,"min_split_loss":-1,"reg_lambda":-1,"silent":-1,"is_main_type":-1}', max_length=1024)),
            ],
            options={
                'verbose_name': 'Тип кассы',
                'verbose_name_plural': 'Типы касс',
            },
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
                ('was_read', models.BooleanField(default=False)),
                ('text', models.CharField(max_length=512)),
                ('type', models.CharField(choices=[('S', 'success'), ('I', 'info'), ('W', 'warning'), ('E', 'error')], default='S', max_length=1)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
                ('to_worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
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
            name='PeriodClients',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_forecast', models.DateTimeField()),
                ('type', models.CharField(choices=[('L', 'Long'), ('S', 'Short'), ('F', 'Fact')], default='L', max_length=1)),
                ('clients', models.FloatField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PeriodDemandChangeLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_from', models.DateTimeField()),
                ('dttm_to', models.DateTimeField()),
                ('multiply_coef', models.FloatField(blank=True, null=True)),
                ('set_value', models.FloatField(blank=True, null=True)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
        ),
        migrations.CreateModel(
            name='PeriodProducts',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_forecast', models.DateTimeField()),
                ('type', models.CharField(choices=[('L', 'Long'), ('S', 'Short'), ('F', 'Fact')], default='L', max_length=1)),
                ('products', models.FloatField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PeriodQueue',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_forecast', models.DateTimeField()),
                ('type', models.CharField(choices=[('L', 'Long'), ('S', 'Short'), ('F', 'Fact')], default='L', max_length=1)),
                ('queue_wait_length', models.FloatField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PeriodVisitors',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_forecast', models.DateTimeField()),
                ('type', models.CharField(choices=[('L', 'Long'), ('S', 'Short'), ('F', 'Fact')], default='L', max_length=1)),
                ('visitors', models.FloatField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ProductionDay',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dt', models.DateField(unique=True)),
                ('type', models.CharField(choices=[('W', 'workday'), ('H', 'holiday'), ('S', 'short workday')], max_length=1)),
                ('is_celebration', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='ProductionMonth',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dt_first', models.DateField()),
                ('total_days', models.SmallIntegerField()),
                ('norm_work_days', models.SmallIntegerField()),
                ('norm_work_hours', models.FloatField()),
            ],
            options={
                'ordering': ('dt_first',),
            },
        ),
        migrations.CreateModel(
            name='Shop',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('full_interface', models.BooleanField(default=True)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('title', models.CharField(max_length=64)),
                ('mean_queue_length', models.FloatField(default=3)),
                ('max_queue_length', models.FloatField(default=7)),
                ('dead_time_part', models.FloatField(default=0.1)),
                ('beta', models.FloatField(default=0.9)),
                ('demand_coef', models.FloatField(default=1)),
                ('forecast_step_minutes', models.TimeField(default=datetime.time(0, 15))),
                ('count_lack', models.BooleanField(default=False)),
                ('method_params', models.CharField(default='[]', max_length=4096)),
                ('cost_weights', models.CharField(default='{}', max_length=4096)),
                ('init_params', models.CharField(default='{"n_working_days_optimal": 20}', max_length=2048)),
                ('break_triplets', models.CharField(default='[]', max_length=1024)),
            ],
            options={
                'verbose_name': 'Отдел',
                'verbose_name_plural': 'Отделы',
            },
        ),
        migrations.CreateModel(
            name='Slot',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('tm_start', models.TimeField(default=datetime.time(7, 0))),
                ('tm_end', models.TimeField(default=datetime.time(23, 59, 59))),
                ('name', models.CharField(blank=True, max_length=32, null=True)),
                ('workers_needed', models.IntegerField(default=1)),
                ('cashbox_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.Shop')),
            ],
            options={
                'verbose_name': 'Слот',
                'verbose_name_plural': 'Слоты',
            },
        ),
        migrations.CreateModel(
            name='SuperShop',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=64, unique=True)),
                ('code', models.CharField(blank=True, max_length=64, null=True)),
                ('dt_opened', models.DateField(blank=True, null=True)),
                ('dt_closed', models.DateField(blank=True, null=True)),
                ('tm_start', models.TimeField(blank=True, default=datetime.time(7, 0), null=True)),
                ('tm_end', models.TimeField(blank=True, default=datetime.time(23, 59, 59), null=True)),
            ],
            options={
                'verbose_name': 'Магазин',
                'verbose_name_plural': 'Магазины',
            },
        ),
        migrations.CreateModel(
            name='Timetable',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('status_message', models.CharField(blank=True, max_length=256, null=True)),
                ('dt', models.DateField()),
                ('status', src.db.utils.EnumField(to_enum=src.db.models.Timetable.Status)),
                ('dttm_status_change', models.DateTimeField()),
                ('task_id', models.CharField(blank=True, max_length=256, null=True)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.Shop')),
            ],
        ),
        migrations.CreateModel(
            name='UserWeekdaySlot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.SmallIntegerField()),
                ('slot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='db.Slot')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='WaitTimeInfo',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dt', models.DateField()),
                ('wait_time', models.PositiveIntegerField()),
                ('proportion', models.FloatField()),
                ('type', models.CharField(choices=[('L', 'Long'), ('S', 'Short'), ('F', 'Fact')], max_length=1)),
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
                ('priority', models.IntegerField(default=0)),
                ('duration', models.FloatField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='WorkerConstraint',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('weekday', models.SmallIntegerField()),
                ('is_lite', models.BooleanField(default=False)),
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
                ('dttm_work_start', models.DateTimeField(blank=True, null=True)),
                ('dttm_work_end', models.DateTimeField(blank=True, null=True)),
                ('tm_break_start', models.TimeField(blank=True, null=True)),
                ('is_manual_tuning', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='WorkerDayCashboxDetails',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('W', 'work period'), ('B', 'rest / break'), ('S', 'study period'), ('Z', 'work in trading floor')], default='W', max_length=1)),
                ('is_tablet', models.BooleanField(default=False)),
                ('dttm_from', models.DateTimeField()),
                ('dttm_to', models.DateTimeField(blank=True, null=True)),
                ('cashbox_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
                ('on_cashbox', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Cashbox')),
                ('worker_day', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.WorkerDay')),
            ],
        ),
        migrations.CreateModel(
            name='WorkerDayChangeRequest',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('status_type', models.CharField(choices=[('A', 'Approved'), ('D', 'Declined'), ('P', 'Pending')], default='P', max_length=1)),
                ('dt', models.DateField()),
                ('type', src.db.utils.EnumField(to_enum=src.db.models.WorkerDay.Type)),
                ('dttm_work_start', models.DateTimeField(blank=True, null=True)),
                ('dttm_work_end', models.DateTimeField(blank=True, null=True)),
                ('tm_break_start', models.TimeField(blank=True, null=True)),
                ('wish_text', models.CharField(blank=True, max_length=512, null=True)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='WorkerMonthStat',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('work_days', models.SmallIntegerField()),
                ('work_hours', models.FloatField()),
                ('month', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.ProductionMonth')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='WorkerPosition',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=64)),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Shop')),
            ],
            options={
                'verbose_name': 'Должность сотрудника',
                'verbose_name_plural': 'Должности сотрудников',
            },
        ),
        migrations.AddField(
            model_name='workerday',
            name='cashbox_types',
            field=models.ManyToManyField(through='db.WorkerDayCashboxDetails', to='db.CashboxType'),
        ),
        migrations.AddField(
            model_name='workerday',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='user_created', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='workerday',
            name='parent_worker_day',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='child', to='db.WorkerDay'),
        ),
        migrations.AddField(
            model_name='workerday',
            name='worker',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='slot',
            name='worker',
            field=models.ManyToManyField(through='db.UserWeekdaySlot', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='shop',
            name='super_shop',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.SuperShop'),
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
            model_name='cameracashbox',
            name='cashbox',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Cashbox'),
        ),
        migrations.AddField(
            model_name='user',
            name='position',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='db.WorkerPosition'),
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
            name='workerdaychangerequest',
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
            unique_together={('super_shop', 'title')},
        ),
    ]
