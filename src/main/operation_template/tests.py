from src.util.test import LocalTestCase, WorkType, datetime
from src.db.models import OperationTemplate, OperationType, PeriodClients
from src.main.operation_template import utils
from datetime import date, time, datetime, timedelta
import json
# from django.test import TestCase

class TestOperationTemplate(LocalTestCase):

    def setUp(self, **args):
        super().setUp(periodclients=False)
        self.operation_type = OperationType.objects.all().first()
        self.dt_from = date(2019, 8, 28)
        self.dt_to = date(2019, 11, 5)

        self.ot_daily = OperationTemplate.objects.create(
            operation_type=self.operation_type,
            name='Ежедневный',
            period=OperationTemplate.PERIOD_DAILY,
            days_in_period='[1,3,5]', #не используются в ежедневном шаблоне
            tm_start=time(10),
            tm_end=time(12),
            value=2.25
        )
        self.ot_weekly = OperationTemplate.objects.create(
            operation_type=self.operation_type,
            name='Еженедельный',
            period=OperationTemplate.PERIOD_WEEKLY,
            days_in_period='[2,3,7]',
            tm_start=time(10),
            tm_end=time(12),
            value=2.25
        )
        self.ot_monthly = OperationTemplate.objects.create(
            operation_type=self.operation_type,
            name='Ежемесячный',
            period=OperationTemplate.PERIOD_MONTHLY,
            days_in_period='[1,3,7,15,28,31]',
            tm_start=time(10),
            tm_end=time(12,30),
            value=2.25
        )
    def create_period_clients(self, dt_from, dt_to):
        while dt_from <= dt_to:
            tm_start = datetime.combine(dt_from,  time(11))
            tm_end = datetime.combine(dt_from,  time(19, 30))
            while tm_start <= tm_end:
                PeriodClients.objects.create(
                    dttm_forecast=tm_start,
                    value=1,
                    type=PeriodClients.LONG_FORECASE_TYPE,
                    operation_type=self.operation_type
                )
                tm_start += timedelta(minutes=30)
            dt_from += timedelta(days=1)

    def test_generate_dates(self):
        dt_from = self.dt_from
        dt_to   = self.dt_to

        dates = list(self.ot_daily.generate_dates(dt_from, dt_to))
        self.assertEqual(len(dates), 70 * 4)

        dates = list(self.ot_weekly.generate_dates(dt_from, dt_to))
        self.assertEqual(len(dates), 10 * 3 * 4)

        dates = list(self.ot_monthly.generate_dates(dt_from, dt_to))
        self.assertEqual(len(dates), 15 * 5)

    def test_build_period_clients_week(self):
        total_days = 15
        ot_days = 6
        times = 4 # периодов в день
        dt_from = datetime.now().date() + timedelta(days=5) #  15 дней
        dt_to = dt_from + timedelta(days=total_days-1)

        self.create_period_clients(dt_from, dt_to)
        pc = PeriodClients.objects.all()
        self.assertEqual(len(pc), total_days * 18)

        # create by operation_template
        utils.build_period_clients(self.ot_weekly, dt_from, dt_to)
        self.assertEqual(len(PeriodClients.objects.all()), total_days * 18 + ot_days * 2)

        #6 дней за 2 недели по часу  - увеличено
        pc=PeriodClients.objects.filter(
            value=3.25
        )
        self.assertEqual(len(pc), ot_days * times / 2 )

        #6 дней за 2 недели по часу  - добавлено
        pc=PeriodClients.objects.filter(
            value=2.25
        )
        self.assertEqual(len(pc), ot_days * times / 2)


        pc=PeriodClients.objects.filter(
            value__gt=1
        ).order_by('dttm_forecast')
        dates = pc.values_list('dttm_forecast', flat=True)

        period_days = json.loads(self.ot_weekly.days_in_period)
        l = len(period_days)
        ind = period_days.index(dates[0].isoweekday())
        ind_dates = 0
        self.assertTrue(ind >= 0)

        while ind_dates < len(dates):
            self.assertEqual(period_days[ind % l], dates[ind_dates].isoweekday())
            ind += 1
            ind_dates += times

        self.assertEqual(dates[0].time(), time(10, 0))
        self.assertEqual(dates[5].time(), time(10, 30))
        self.assertEqual(dates[10].time(), time(11, 0))

        # delete by operation_template
        utils.build_period_clients(
            self.ot_weekly,
            dt_from,
            dt_to,
            operation='delete')

        pc=PeriodClients.objects.filter(
            value=1
        )
        self.assertEqual(len(pc), total_days * 18)

        pc=PeriodClients.objects.filter(
            value=0
        )
        self.assertEqual(len(pc), ot_days * 2)

    def test_build_period_clients_month(self):
        total_days = 62
        times = 5 # периодов в день

        dt_from = datetime.now().date() + timedelta(days=5)
        dt_to = dt_from + timedelta(days=total_days-1)

        dates = [d for d in self.ot_monthly.generate_dates(dt_from, dt_to)]

        #Количество дней по шаблону за период
        ot_days = len([d for d in self.ot_monthly.generate_dates(dt_from, dt_to)]) / times


        self.create_period_clients(dt_from, dt_to)
        pc = PeriodClients.objects.all()
        self.assertEqual(len(pc), total_days * 18 )

        # create by operation_template
        utils.build_period_clients(self.ot_monthly, dt_from, dt_to)
        self.assertEqual(len(PeriodClients.objects.all()), total_days * 18 + ot_days * 2)


        pc=PeriodClients.objects.filter(value=3.25)
        self.assertEqual(len(pc), ot_days * 3 )


        pc=PeriodClients.objects.filter(value=2.25)
        self.assertEqual(len(pc), ot_days * 2 )


        pc=PeriodClients.objects.filter(value__gt=1).order_by('dttm_forecast')
        dates = pc.values_list('dttm_forecast', flat=True)

        self.assertTrue(dates[0].day in json.loads(self.ot_monthly.days_in_period))
        self.assertTrue(dates[6].day in json.loads(self.ot_monthly.days_in_period))
        self.assertTrue(dates[12].day in json.loads(self.ot_monthly.days_in_period))

        self.assertEqual(dates[0].time(), time(10, 0))
        self.assertEqual(dates[6].time(), time(10, 30))
        self.assertEqual(dates[12].time(), time(11, 0))

        # delete by operation_template
        utils.build_period_clients(
            self.ot_monthly,
            dt_from,
            dt_to,
            operation='delete')

        pc=PeriodClients.objects.filter(
            value=1
        )
        self.assertEqual(len(pc), 62 * 18)

        pc=PeriodClients.objects.filter(
            value=0
        )
        self.assertEqual(len(pc), ot_days * 2)
