import datetime

from src.util.test import LocalTestCase
from src.db.models import WorkerMonthStat
from .tasks import update_worker_month_stat


class TestCelery(LocalTestCase):

    def setUp(self):
        super().setUp()

    def test_update_worker_month_stat(self):
        update_worker_month_stat()
        status = WorkerMonthStat.objects.all()
        self.assertEqual(status[0].worker.username, 'user1')
        self.assertEqual(status[0].month.dt_first, datetime.date(2018, 6, 1))
        self.assertEqual(status[0].work_days, 20)
        self.assertEqual(status[0].work_hours, 195)

        self.assertEqual(status[1].worker.username, 'user1')
        self.assertEqual(status[1].month.dt_first, datetime.date(2018, 7, 1))
        self.assertEqual(status[1].work_days, 20)
        self.assertEqual(status[1].work_hours, 195)

        self.assertEqual(status[2].worker.username, 'user2')
        self.assertEqual(status[2].month.dt_first, datetime.date(2018, 6, 1))
        self.assertEqual(status[2].work_days, 20)
        self.assertEqual(status[2].work_hours, 195)

        self.assertEqual(status[3].worker.username, 'user3')
        self.assertEqual(status[3].month.dt_first, datetime.date(2018, 6, 1))
        self.assertEqual(status[3].work_days, 20)
        self.assertEqual(status[3].work_hours, 195)

        self.assertEqual(status[4].worker.username, 'user3')
        self.assertEqual(status[4].month.dt_first, datetime.date(2018, 7, 1))
        self.assertEqual(status[4].work_days, 11)
        self.assertEqual(status[4].work_hours, 107.25)

