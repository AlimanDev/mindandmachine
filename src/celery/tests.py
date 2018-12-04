import datetime
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta
from src.util.test import LocalTestCase
from src.db.models import (
    WorkerCashboxInfo,
    CashboxType,
    WorkerDayCashboxDetails,
    PeriodQueues,
    IncomeVisitors,
    EmptyOutcomeVisitors,
    PurchasesOutcomeVisitors,
    Notifications,
    CameraCashboxStat,
    Shop,
)
from .tasks import (
    update_worker_month_stat,
    allocation_of_time_for_work_on_cashbox,
    update_queue,
    update_visitors_info,
    release_all_workers,
    notify_cashiers_lack,
    clean_camera_stats,
    create_pred_bills,
)


class TestCelery(LocalTestCase):

    def setUp(self):
        super().setUp()

        months_ago = now() - relativedelta(months=3)
        for i in range(100):
            CameraCashboxStat.objects.create(
                camera_cashbox=self.camera_cashbox,
                dttm=months_ago - datetime.timedelta(hours=i),
                queue=i
            )

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

    def test_update_queue(self):
        dttm_now = now()

        if not len(CashboxType.objects.filter(dttm_last_update_queue__isnull=False)):
            with self.assertRaises(ValueError) as cm:
                update_queue()
            raise Exception(cm.exception)

        update_queue()

        updated_cashbox_types = CashboxType.objects.\
            qos_filter_active(
                dttm_now + datetime.timedelta(minutes=30), dttm_now).\
            filter(
                dttm_last_update_queue__isnull=False,
            )
        for update_time in updated_cashbox_types.values_list('dttm_last_update_queue', flat=True):
            self.assertEqual(
                update_time,
                dttm_now.replace(minute=0 if dttm_now.minute < 30 else 30, second=0, microsecond=0)
            )
        for cashbox_type in CashboxType.objects.filter(dttm_deleted__isnull=False):
            self.assertEqual(cashbox_type.dttm_last_update_queue, None)
        self.assertGreater(PeriodQueues.objects.count(), 0)

    def test_update_visitors_info(self):
        def check_amount(model, dttm):
            return model.objects.filter(dttm_forecast=dttm, type=PeriodQueues.FACT_TYPE).count()

        dttm_now = now()
        dttm = now().replace(minute=0 if dttm_now.minute < 30 else 30, second=0, microsecond=0)
        update_visitors_info()

        self.assertEqual(check_amount(IncomeVisitors, dttm), 1)
        self.assertEqual(check_amount(EmptyOutcomeVisitors, dttm), 1)
        self.assertEqual(check_amount(PurchasesOutcomeVisitors, dttm), 1)

    def test_release_all_workers(self):
        release_all_workers()
        amount_of_unreleased_workers = WorkerDayCashboxDetails.objects.filter(dttm_to__isnull=True).count()
        self.assertEqual(amount_of_unreleased_workers, 0)

    def test_notify_cashiers_lack(self):
        dt_now = now().date()
        existing_notifications = Notifications.objects.all()  # если где-то в тестах еще будут уведомления
        Notifications.objects.all().delete()

        notify_cashiers_lack()  # при стандартном наборе тестовых данных будет хотя бы 1 уведомление
        self.assertGreater(Notifications.objects.count(), 0)
        Notifications.objects.all().delete()
        # терь добавим 100 сотрудников, чтобы точно перекрыть нехватку
        self.create_many_users(100, dt_now - datetime.timedelta(days=15), dt_now + datetime.timedelta(days=15))
        self.assertEqual(Notifications.objects.count(), 0)  # уведомление о нехватке должно стать 0

        Notifications.objects.all().delete()  # удаляем только что созданные
        Notifications.objects.bulk_create(existing_notifications)  # возвращаем те, которые были до этого

    def test_allocation_of_time_for_work_on_cashbox(self):
        allocation_of_time_for_work_on_cashbox()
        x = WorkerCashboxInfo.objects.all()
        self.assertEqual(x[0].duration, 0)
        self.assertEqual(x[1].duration, 0)
        self.assertEqual(x[2].duration, 0)
        self.assertGreater(x[3].duration, 0)

    def test_create_pred_bills(self):
        from django.core.exceptions import EmptyResultSet
        try:
            create_pred_bills()
        except EmptyResultSet:
            pass

    def test_clean_camera_stats(self):
        stats = CameraCashboxStat.objects.filter(dttm__lt=now() - relativedelta(months=3))
        self.assertEqual(stats.count(), 100)
        clean_camera_stats()
        stats = CameraCashboxStat.objects.filter(dttm__lt=now() - relativedelta(months=3))
        self.assertEqual(stats.count(), 0)
