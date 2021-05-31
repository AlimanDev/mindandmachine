import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from datetime import time, datetime, timedelta, date

from src.conf.djconfig import BASE_DIR
from src.base.models import (
    Shop,
    Region,
    User,
    Group,
    Employment,
    Employee,
    Network,
)
from src.forecast.models import (
    OperationType,
    OperationTypeName,
    PeriodClients,
)
from src.timetable.models import (
    WorkType,
    WorkTypeName,
    ExchangeSettings,
)
from etc.scripts import fill_calendar
from etc.scripts.create_access_groups import password_generator, update_group_functions
from dateutil.relativedelta import relativedelta

def fill_demand(shop):
    period_clients = []
    dt_from = date.today().replace(day=1)
    dt_to = dt_from + relativedelta(months=2)
    dttms = [
        datetime.combine(dt_from + timedelta(i), time(j))
        for i in range((dt_to - dt_from).days)
        for j in range(24)
    ]
    period_clients = [
        PeriodClients(
            value=1,
            operation_type=o_type,
            type=PeriodClients.LONG_FORECASE_TYPE,
            dttm_forecast=dttm,
        )
        for o_type in OperationType.objects.filter(work_type__shop=shop)
        for dttm in dttms
    ]
    PeriodClients.objects.bulk_create(period_clients)

class Command(BaseCommand):
    help = 'Add DB data for client'

    def add_arguments(self, parser):
        parser.add_argument('--need_test_shop', help='Creates test shop', type=bool, default=False)
        parser.add_argument('--client_name', help='Name of client', type=str)
        parser.add_argument('--work_types', help='Work types with , separator', type=str)

    def handle(self, *args, **options):
        if options.get('work_types'):
            try:
                work_types = options.get('work_types').split(',')
            except:
                raise CommandError('Bad work types format.')
        else:
            work_types = ['Кассы', 'Торговый зал']
        with transaction.atomic():
            network = Network.objects.first()
            if options.get('client_name'):
                network.name = options.get('client_name')
                network.save()
            region, _ = Region.objects.get_or_create(
                network=network,
                defaults={
                    'name': "Регион 1",
                }
            )
            fill_calendar.fill_days('2020.1.1', (datetime.now() + timedelta(days=730)).date().strftime('%Y.%m.%d'), 1, file_name=os.path.join(BASE_DIR, 'etc/scripts/work_data.csv'))
            super_shop = Shop.objects.first()
            super_shop.name = options.get('client_name') or 'Корневой магазин'
            super_shop.save()
            update_group_functions(network=network, path=os.path.join(BASE_DIR, 'etc/scripts/function_group_default.xlsx'))
            admin = User.objects.create(
                is_staff=True,
                is_superuser=True,
                username='qadmin',
                first_name='Admin',
                last_name='Admin',
                network=network,
            )
            admin_employee = Employee.objects.create(
                user=admin,
                tabel_code='admin',
            )
            Employment.objects.create(
                employee=admin_employee,
                function_group=Group.objects.get(name='Администратор'),
                dt_hired=date.today(),
                shop=super_shop,
            )
            u_pass = password_generator()
            admin.set_password(u_pass)
            admin.save()
            self.stdout.write(self.style.WARNING('admin login: {}, password: {}'.format('qadmin', u_pass)))
            work_type_names = {}
            operation_type_names = {}
            last_work_type_code = 0
            last_operation_type_code = 0
            for work_type in work_types:
                last_work_type_code += 1
                work_type_names[work_type] = WorkTypeName.objects.create(
                    name=work_type,
                    code=last_work_type_code,
                    network=network,
                )
                last_operation_type_code += 1
                operation_type_names[work_type] = OperationTypeName.objects.create(
                    name=work_type,
                    code=last_operation_type_code,
                    network=network,
                    work_type_name=work_type_names[work_type],
                )
            if options.get('need_test_shop'):
                shop = Shop.objects.create(
                    parent_id=super_shop.id,
                    name='Тестовый отдел',
                    forecast_step_minutes=time(hour=1),
                    region_id=region.id,
                    tm_open_dict='{"all":"07:00:00"}',
                    tm_close_dict='{"all":"23:00:00"}',
                    network=network,
                )
                for i in range(5):
                    u = User.objects.create(
                        username=password_generator(),
                        first_name=f'{i + 1}',
                        last_name='сотрудник',
                        middle_name='',
                        network=network,
                    )
                    u.username = f'u{u.id}'
                    u.save()
                    employee = Employee.objects.create(
                        user=u,
                        tabel_code=u.username,
                    )
                    Employment.objects.create(
                        employee=employee,
                        dt_hired=date(2019, 1, 1),
                        shop=shop,
                    )
                operation_types = []
                for wt in work_types:
                    work_type = WorkType.objects.create(work_type_name=work_type_names[wt], shop_id=shop.id)
                    operation_types.append(OperationType(operation_type_name=operation_type_names[wt], work_type=work_type))
                OperationType.objects.bulk_create(operation_types)
                fill_demand(shop)
            Shop.objects.rebuild()
            ExchangeSettings.objects.create(network=network)
            self.stdout.write(self.style.SUCCESS('Successfully filled database. Created {} work types.'.format(WorkTypeName.objects.count())))
