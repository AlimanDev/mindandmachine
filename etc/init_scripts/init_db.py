if __name__ == "__main__":
    import sys
    sys.path.append('../../')
    import os, django, argparse
    parser = argparse.ArgumentParser(description='Add DB data for client')
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.conf.djconfig")
    parser.add_argument('--lang', help='Language of client', default='ru')
    parser.add_argument('--need_test_shop', help='Creates test shop', type=bool, default=False)


    args = parser.parse_args()
    django.setup()

    


import json
from datetime import time, datetime, timedelta, date
from src.apps.base.models import (
    Shop,
    Region,
    User,
    Group,
    Employment,
    Network,
    Employee
)
from src.apps.forecast.models import (
    OperationType,
    PeriodClients,
)
from src.apps.timetable.models import (
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

algo_params = json.dumps([
    { 	
        "algo_init": { 		
            "time_factor_mul": 2.0, 		
            "performance_factor_mul": 2.5, 		
            "min_necessary_workers_in_period": 1, 		
            "use_custom_week": True, 		
            "min_workdays_amount": 2, 		
            "max_workdays_amount": 4, 		
            "min_holidays_amount": 2, 		
            "max_holidays_amount": 3, 		
            "use_start_work_fitness_1": False, 		
            "idle_fitness_mul_1": 200.0, 		
            "idle_fitness_mul_2": 1000.0 	
        }, 	
        "algo_run": {}, 	
        "algo_name": "slots-core" 
    }
])


def main(lang='ru', need_test_shop=False):
    network = Network.objects.first()
    region = Region.objects.create(
        name=f"Регион 1",
        network=network
    )
    fill_calendar.fill_days('2020.1.1', (datetime.now() + timedelta(days=730)).date().strftime('%Y.%m.%d'), 1, file_name='../scripts/work_data.csv')
    super_shop = Shop.objects.first()
    super_shop.name = 'Корневой магазин'
    super_shop.save()
    update_group_functions(network=network, path='../scripts/function_group_default.xlsx')
    admin = User.objects.create(
        is_staff=True,
        is_superuser=True,
        username='qadmin',
        first_name='Admin',
        last_name='Admin',
        network=network,
    )
    admin_e = Employee.objects.create(
        user=admin
    )
    admin_group = Group.objects.get(name='Администратор')
    Employment.objects.create(
        employee=admin_e,
        function_group=admin_group,
        dt_hired=date.today(),
        shop=super_shop,
    )
    u_pass = password_generator()
    admin.set_password(u_pass)
    admin.save()
    print(f'admin login: {admin.username}, password: {u_pass}')
    if need_test_shop:
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
            e = Employee.objects.create(user=u)
            Employment.objects.create(
                employee=e,
                dt_hired=date(2019, 1, 1),
                shop=shop,
            )
        last_work_type_code = 0
        work_types = ['Кассы', 'Торговый зал']
        work_type_names = {}
        for work_type in work_types:
            if work_type not in work_type_names:
                last_work_type_code += 1
                work_type_names[work_type] =  WorkTypeName.objects.create(
                    name=work_type,
                    code=last_work_type_code,
                    network=network,
                )
            work_type = WorkType.objects.create(work_type_name=work_type_names[work_type], shop_id=shop.id)
        fill_demand(shop)
    Shop.objects.rebuild()
    ExchangeSettings.objects.create(network=network)


if __name__ == "__main__":
    main(lang=args.lang, need_test_shop=args.need_test_shop)