import datetime
from django.utils.timezone import now
from src.util.test import LocalTestCase
from src.db.models import (
    WorkerMonthStat,
    WorkerCashboxInfo,
    CashboxType,
    WorkerDayCashboxDetails,
    PeriodQueues,
)
from .tasks import (
    update_worker_month_stat,
    allocation_of_time_for_work_on_cashbox,
    update_queue
)


class TestCelery(LocalTestCase):

    def setUp(self):
        super().setUp()
        dttm_start = datetime.datetime.combine(datetime.date(2018, 12, 1), datetime.time(9, 0, 0))
        dttm_end = datetime.datetime.combine(datetime.date(2018, 12, 1), datetime.time(18, 0, 0))
        for i in range(15):
            try:
                WorkerDayCashboxDetails.objects.create(
                    status=WorkerDayCashboxDetails.TYPE_WORK,
                    worker_day=self.worker_day4,
                    on_cashbox=self.cashbox2,
                    cashbox_type=self.cashboxType1,
                    is_tablet=True,
                    dttm_from=dttm_start,
                    dttm_to=dttm_end,
                )
            except Exception:
                pass

    # def test_update_worker_month_stat(self):
    #     update_worker_month_stat()
    #     worker_month_stat = WorkerMonthStat.objects.all()
    #     self.assertEqual(worker_month_stat[0].worker.username, 'user1')
    #     self.assertEqual(worker_month_stat[0].month.dt_first, datetime.date(2018, 12, 1))
    #     self.assertEqual(worker_month_stat[0].work_days, 20)
    #     self.assertEqual(worker_month_stat[0].work_hours, 195)
    #
    #     self.assertEqual(worker_month_stat[1].worker.username, 'user1')
    #     self.assertEqual(worker_month_stat[1].month.dt_first, datetime.date(2018, 12, 1))
    #     self.assertEqual(worker_month_stat[1].work_days, 20)
    #     self.assertEqual(worker_month_stat[1].work_hours, 195)
    #
    #     self.assertEqual(worker_month_stat[2].worker.username, 'user2')
    #     self.assertEqual(worker_month_stat[2].month.dt_first, datetime.date(2018, 12, 1))
    #     self.assertEqual(worker_month_stat[2].work_days, 20)
    #     self.assertEqual(worker_month_stat[2].work_hours, 195)
    #
    #     self.assertEqual(worker_month_stat[3].worker.username, 'user3')
    #     self.assertEqual(worker_month_stat[3].month.dt_first, datetime.date(2018, 12, 1))
    #     self.assertEqual(worker_month_stat[3].work_days, 20)
    #     self.assertEqual(worker_month_stat[3].work_hours, 195)
    #
    #     self.assertEqual(worker_month_stat[4].worker.username, 'user3')
    #     self.assertEqual(worker_month_stat[4].month.dt_first, datetime.date(2018, 12, 1))
    #     self.assertEqual(worker_month_stat[4].work_days, 20)
    #     self.assertEqual(worker_month_stat[4].work_hours, 179.25)
    #
    # def test_allocation_of_time_for_work_on_cashbox(self):
    #     allocation_of_time_for_work_on_cashbox()
    #     x = WorkerCashboxInfo.objects.all()
    #     self.assertEqual(x[0].duration, 0)
    #     self.assertEqual(x[1].duration, 0)
    #     self.assertEqual(x[2].duration, 0)
    #     # self.assertEqual(x[3].duration, 180)

    def test_update_queue(self):
        dttm_now = now()

        if not len(CashboxType.objects.filter(dttm_last_update_queue__isnull=False)):
            with self.assertRaises(ValueError) as cm:
                update_queue()
            raise Exception(cm.exception)

        update_queue()

        updated_cashbox_types = CashboxType.objects.qos_filter_active(dttm_now + datetime.timedelta(minutes=30), dttm_now).filter(
            dttm_last_update_queue__isnull=False,
        )
        for update_time in updated_cashbox_types.values_list('dttm_last_update_queue', flat=True):
            self.assertEqual(
                update_time,
                dttm_now.replace(minute=0 if dttm_now.minute < 30 else 30, second=0, microsecond=0)
            )
        for cashbox_type in CashboxType.objects.filter(dttm_deleted__isnull=False):
            self.assertEqual(cashbox_type.dttm_last_update_queue, None)
        self.assertTrue(PeriodQueues.objects.count() > 0)
