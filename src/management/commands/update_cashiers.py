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
        new_data = joblib.load(filename=options['infile'])
        for entry in new_data.iterrows():
            _, data = entry
            cashier_name = data['index']
            if cashier_name not in cashiers_map:
                print('There is no such user: {}'.format(data['index']))
            else:
                cashier = cashiers_map[cashier_name]
                # update speed
                speeds = data['types_speeds']
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
                new_work_type = worktype_translation.get(data['type'], User.WorkType.TYPE_5_2.value)
                cashier.work_type = new_work_type
                cashier.save()

                # update contraints
                WorkerConstraint.objects.filter(worker=cashier).delete()
                first_monday = 3
                constraints = []
                for weekday in range(7):
                    # склеиваем constraints, т.к. они по 15 минут, а в базе по 30
                    new_constraints = data['constraints'][first_monday + weekday][::2]
                    time = datetime.datetime(year=1971, month=1, day=1)
                    time_step = datetime.timedelta(minutes=30)
                    for constraint in new_constraints:
                        # никто не работает до 7 и после 00:00
                        if constraint or time.hour < 7:
                            constraints.append(WorkerConstraint(
                                worker=cashier,
                                weekday=weekday,
                                tm=time
                            ))
                        time += time_step

                WorkerConstraint.objects.bulk_create(constraints)