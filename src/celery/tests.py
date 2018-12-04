import datetime
from django.utils.timezone import now
from src.util.test import LocalTestCase, create_user
from src.db.models import (
    WorkerMonthStat,
    WorkerCashboxInfo,
    CashboxType,
    WorkerDayCashboxDetails,
    PeriodQueues,
    CameraClientEvent,
    CameraClientGate,
    IncomeVisitors,
    EmptyOutcomeVisitors,
    PurchasesOutcomeVisitors,
    WorkerDay,
    PeriodClients,
    User,
    Notifications,
)
from .tasks import (
    update_worker_month_stat,
    allocation_of_time_for_work_on_cashbox,
    update_queue,
    update_visitors_info,
    release_all_workers,
    notify_cashiers_lack,
)


class TestCelery(LocalTestCase):

    def setUp(self):
        super().setUp()
        dttm_now = now()
        dttm_start = datetime.datetime(2018, 12, 1, 9, 0, 0)
        dttm_end = datetime.datetime(2018, 12, 1, 18, 0, 0)

        entry_gate = CameraClientGate.objects.create(type=CameraClientGate.TYPE_ENTRY, name='Вход')
        exit_gate = CameraClientGate.objects.create(type=CameraClientGate.TYPE_OUT, name='Выход')

        worker_day = WorkerDay.objects.create(
            worker=self.user1,
            dt=(dttm_now - datetime.timedelta(days=1)).date(),
            type=WorkerDay.Type.TYPE_WORKDAY.value,
            dttm_work_start=dttm_start,
            dttm_work_end=dttm_end
        )

        gates = [entry_gate, exit_gate]

        amount = 10

        dt_from = dttm_now.date() - datetime.timedelta(days=amount / 2)
        dt_to = dttm_now.date() + datetime.timedelta(days=amount / 2)
        for i in range(amount):
            user = User.objects.create(
                id=1000+i,
                last_name='user_{}'.format(1000+i),
                shop=self.shop,
                first_name='Иван',
                username='user_{}'.format(1000+i),
            )
            for j in range(amount):
                dt = dt_from + datetime.timedelta(days=j)
                wd = WorkerDay.objects.create(
                    dttm_work_start=datetime.datetime.combine(dt, dttm_start.time()),
                    dttm_work_end=datetime.datetime.combine(dt, dttm_end.time()),
                    type=WorkerDay.Type.TYPE_WORKDAY.value,
                    dt=dt,
                    worker=user
                )
                WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    on_cashbox=self.cashbox1,
                    cashbox_type=self.cashboxType1,
                    dttm_from=wd.dttm_work_start,
                    dttm_to=wd.dttm_work_end
                )

        while dt_from < dt_to:
            start_dttm = datetime.datetime.combine(dt_from, datetime.time(hour=7, minute=0))
            for i in range(15*2 + 1):  # 15 hours => from 7:00 till 7+15=22:00
                PeriodClients.objects.create(
                    dttm_forecast=start_dttm + datetime.timedelta(minutes=30*i),
                    cashbox_type=self.cashboxType1,
                    type=PeriodClients.LONG_FORECASE_TYPE,
                    value=100 + (-1)**(i % 2) * i
                )
            dt_from += datetime.timedelta(days=1)
        for i in range(15):
            try:
                WorkerDayCashboxDetails.objects.create(
                    status=WorkerDayCashboxDetails.TYPE_WORK,
                    worker_day=worker_day,
                    on_cashbox=self.cashbox2,
                    cashbox_type=self.cashboxType1,
                    is_tablet=True,
                    dttm_from=dttm_start,
                    dttm_to=dttm_end if i % 5 != 0 else None,
                )
                CameraClientEvent.objects.create(
                    dttm=dttm_now - datetime.timedelta(minutes=2*i),
                    gate=gates[i % 2],
                    type=CameraClientEvent.DIRECTION_TYPES[i % 2][0],  # TOWARD / BACKWARD
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
        existing_notifications = Notifications.objects.all()  # если где-то в тестах еще будут уведомления
        Notifications.objects.all().delete()
        notify_cashiers_lack()
        self.assertGreater(Notifications.objects.count(), 0)
        Notifications.objects.all().delete()  # удаляем только что созданные
        Notifications.objects.bulk_create(existing_notifications)  # возвращаем те, которые были до этого

    def test_allocation_of_time_for_work_on_cashbox(self):
        allocation_of_time_for_work_on_cashbox()
        x = WorkerCashboxInfo.objects.all()
        print(x.values_list('duration', flat=True))
        # self.assertEqual(x[0].duration, 0)
        # self.assertEqual(x[1].duration, 0)
        # self.assertEqual(x[2].duration, 0)
        # self.assertEqual(x[3].duration, 180)
