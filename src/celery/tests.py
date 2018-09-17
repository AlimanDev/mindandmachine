import datetime

from src.util.test import LocalTestCase
from src.db.models import WorkerMonthStat, WorkerDayCashboxDetails
from .tasks import update_worker_month_stat, allocation_of_time_for_work_on_cashbox, WorkerCashboxInfo


class TestCelery(LocalTestCase):

    def setUp(self):
        super().setUp()
        for i in range(1, 21):
            try:

                WorkerDayCashboxDetails.objects.create(
                    status=WorkerDayCashboxDetails.TYPE_WORK,
                    worker_day=self.worker_day4,
                    on_cashbox=self.cashbox2,
                    cashbox_type=self.cashboxType1,
                    is_tablet=True,
                    dttm_from=datetime.datetime.combine(datetime.date(2018, 7, 21), datetime.time(9, 0, 0)),
                    dttm_to=datetime.datetime.combine(datetime.date(2018, 7, 21), datetime.time(18, 0, 0)),
                )
            except Exception:
                pass

    def test_update_worker_month_stat(self):
        update_worker_month_stat()
        worker_month_stat = WorkerMonthStat.objects.all()
        self.assertEqual(worker_month_stat[0].worker.username, 'user1')
        self.assertEqual(worker_month_stat[0].month.dt_first, datetime.date(2018, 6, 1))
        self.assertEqual(worker_month_stat[0].work_days, 20)
        self.assertEqual(worker_month_stat[0].work_hours, 195)

        self.assertEqual(worker_month_stat[1].worker.username, 'user1')
        self.assertEqual(worker_month_stat[1].month.dt_first, datetime.date(2018, 7, 1))
        self.assertEqual(worker_month_stat[1].work_days, 20)
        self.assertEqual(worker_month_stat[1].work_hours, 195)

        self.assertEqual(worker_month_stat[2].worker.username, 'user2')
        self.assertEqual(worker_month_stat[2].month.dt_first, datetime.date(2018, 6, 1))
        self.assertEqual(worker_month_stat[2].work_days, 20)
        self.assertEqual(worker_month_stat[2].work_hours, 195)

        self.assertEqual(worker_month_stat[3].worker.username, 'user3')
        self.assertEqual(worker_month_stat[3].month.dt_first, datetime.date(2018, 6, 1))
        self.assertEqual(worker_month_stat[3].work_days, 20)
        self.assertEqual(worker_month_stat[3].work_hours, 195)

        self.assertEqual(worker_month_stat[4].worker.username, 'user3')
        self.assertEqual(worker_month_stat[4].month.dt_first, datetime.date(2018, 7, 1))
        self.assertEqual(worker_month_stat[4].work_days, 20)
        self.assertEqual(worker_month_stat[4].work_hours, 179.25)

    def test_allocation_of_time_for_work_on_cashbox(self):
        allocation_of_time_for_work_on_cashbox()
        x = WorkerCashboxInfo.objects.all()
        self.assertEqual(x[0].duration, 0)
        self.assertEqual(x[1].duration, 0)
        self.assertEqual(x[2].duration, 0)
        self.assertEqual(x[3].duration, 180)
