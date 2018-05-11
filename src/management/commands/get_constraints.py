import datetime
import pandas
import numpy
from django.core.management.base import BaseCommand, CommandError
from src.db.models import Shop, Slot, User, WorkerConstraint

class Command(BaseCommand):
    help = 'print to excel file users constraints in department'

    START_H = 7

    def __create_tm(self, num, step_minutes=30):
        dttm = datetime.datetime(2018, 1, 1, self.START_H, 0) + datetime.timedelta(seconds=step_minutes * num * 60)
        return dttm.strftime("%H:%M")

    def __tm2ind(self, tm, step_minutes=30):
        dttm = datetime.datetime(2018, 1, 1, self.START_H, 0)
        dttm_r = datetime.datetime(2018, 1, 1, tm.hour, tm.minute)
        return int((dttm_r - dttm).total_seconds()) // 60 // step_minutes

    def add_arguments(self, parser):
        parser.add_argument('shop_id', type=str)
        parser.add_argument('out_file', type=str)

    def handle(self, *args, **options):
        AMOUNT = (24-7) * 2
        weekdays = ['пн', 'вт', 'ср',  'чт', 'пт', 'сб', 'вс']
        tms = [self.__create_tm(i) for i in range(AMOUNT)]
        writer = pandas.ExcelWriter(options['out_file'], engine='xlsxwriter')

        shop = Shop.objects.get(id=options['shop_id'])

        for u in User.objects.filter(shop=shop):
            table = numpy.zeros((7, AMOUNT))
            for constr in WorkerConstraint.objects.filter(worker=u):
                if self.START_H <= constr.tm.hour:
                    table[constr.weekday, self.__tm2ind(constr.tm)] = 1

            df = pandas.DataFrame(table, columns=tms, index=weekdays)
            df.to_excel(writer, sheet_name='{}_{}'.format(u.first_name, u.last_name))

