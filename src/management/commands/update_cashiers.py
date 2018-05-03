import joblib
import datetime
from django.core.management.base import BaseCommand, CommandError
from src.db.models import User, WorkerCashboxInfo, WorkerConstraint

class Command(BaseCommand):
    help = 'Update cashier info'

    def add_arguments(self, parser):
        parser.add_argument('infile', type=str)
        parser.add_argument('shop_id', type=str)

    def handle(self, *args, **options):
        # select all cashiers
        cashiers_map = {}
        cashiers = User.objects.filter(shop__title='Кассиры', shop__super_shop__code=options['shop_id'])
        for cashier in cashiers:
            name = '{} {} {}'.format(cashier.last_name, cashier.first_name, cashier.middle_name)
            cashiers_map[name] = cashier

        # load new data
        new_cashiers_data = joblib.load(filename=options['infile'])
        for new_cashier_data_entry in new_cashiers_data.iterrows():
            _, new_cashier_data = new_cashier_data_entry
            cashier_name = new_cashier_data['index']
            if cashier_name not in cashiers_map:
                print('There is no such user: {}'.format(new_cashier_data['index']))
            else:
                cashier = cashiers_map[cashier_name]
                # update speed
                speeds = new_cashier_data['types_speeds']
                for speed_type, speed_value in speeds.items():
                    speed_translation = {
                        'usual': 'Линия',
                        'return': 'Возврат',
                        'deli': 'Доставка',
                        'info': 'Информация'
                    }
                    if speed_type not in speed_translation:
                        print('unknown speed type: {}'.format(speed_type))
                    else:
                        WorkerCashboxInfo.objects\
                            .filter(worker=cashier, cashbox_type__name=speed_translation[speed_type])\
                            .update(mean_speed=speed_value)

                # update work time
                worktype_translation = {
                    '5/2': User.WorkType.TYPE_5_2.value,
                    '2/5': User.WorkType.TYPE_2_2.value,
                    '3/4': User.WorkType.TYPE_2_2.value,
                    '4/3': User.WorkType.TYPE_5_2.value,
                    '2/2': User.WorkType.TYPE_2_2.value
                }
                new_work_type = worktype_translation.get(new_cashier_data['type'], User.WorkType.TYPE_5_2.value)
                cashier.work_type = new_work_type
                cashier.save()

                # update contraints
                WorkerConstraint.objects.filter(worker=cashier).delete()
                first_monday = 3
                constraints = []
                for weekday in range(7):
                    # склеиваем constraints, т.к. они по 15 минут, а в базе по 30
                    time = datetime.datetime(year=1971, month=1, day=1)
                    time_step = datetime.timedelta(minutes=30)
                    # никто не работает до 7:00
                    while time.hour < 7:
                        constraints.append(WorkerConstraint(
                            worker=cashier,
                            weekday=weekday,
                            tm=time
                        ))
                        time += time_step
                    new_constraints = new_cashier_data['constraints'][first_monday + weekday][::2]
                    for constraint in new_constraints:
                        if constraint:
                            constraints.append(WorkerConstraint(
                                worker=cashier,
                                weekday=weekday,
                                tm=time
                            ))
                        time += time_step

                WorkerConstraint.objects.bulk_create(constraints)