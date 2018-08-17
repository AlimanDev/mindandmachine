import datetime

from src.util.test import LocalTestCase
from src.db.models import WorkerMonthStat
from .tasks import update_worker_month_stat, allocation_of_time_for_work_on_cashbox, WorkerCashboxInfo


class TestCelery(LocalTestCase):

    def setUp(self):
        super().setUp()

    def test_update_worker_month_stat(self):
        update_worker_month_stat()
        worker_month_stat = WorkerMonthStat.objects.all()
        self.assertEqual(worker_month_stat[0].worker.username, 'user1')
        self.assertEqual(worker_month_stat[0].month.dt_first, datetime.date(2018, 6, 1))
        self.assertEqual(worker_month_stat[0].work_days,  20)
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
        for item in x:
            print(item.worker_id, item.duration, item.cashbox_type_id)
