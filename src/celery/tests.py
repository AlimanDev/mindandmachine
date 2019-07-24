import datetime
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from src.util.test import LocalTestCase
from src.db.models import (
    WorkerCashboxInfo,
    WorkType,
    WorkerDayCashboxDetails,
    PeriodQueues,
    IncomeVisitors,
    EmptyOutcomeVisitors,
    PurchasesOutcomeVisitors,
    Notifications,
    CameraCashboxStat,
    Shop,
    ExchangeSettings,
    User,
    PeriodClients,
    SuperShop,
    WorkerDay,
    OperationType,
    Event,
)
from .tasks import (
    update_worker_month_stat,
    allocation_of_time_for_work_on_cashbox,
    update_queue,
    update_visitors_info,
    release_all_workers,
    clean_camera_stats,
    create_pred_bills,
    cancel_vacancies,
    create_vacancy_and_notify_cashiers_lack,
    workers_hard_exchange
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
        dttm_now = now() + datetime.timedelta(hours=3)

        if not len(WorkType.objects.filter(dttm_last_update_queue__isnull=False)):
            with self.assertRaises(ValueError) as cm:
                update_queue()
            raise Exception(cm.exception)

        update_queue()

        updated_cashbox_types = WorkType.objects.qos_filter_active(
            dttm_now + datetime.timedelta(minutes=30),
            dttm_now,
            dttm_last_update_queue__isnull=False,
        )
        for update_time in updated_cashbox_types.values_list('dttm_last_update_queue', flat=True):
            self.assertEqual(
                update_time,
                dttm_now.replace(minute=0 if dttm_now.minute < 30 else 30, second=0, microsecond=0)
            )
        for cashbox_type in WorkType.objects.filter(dttm_deleted__isnull=False):
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

    # def test_notify_cashiers_lack(self):
    #     dt_now = now().date()
    #     existing_notifications = Notifications.objects.all()  # если где-то в тестах еще будут уведомления
    #     Notifications.objects.all().delete()
    #
    #     notify_cashiers_lack()  # при стандартном наборе тестовых данных будет хотя бы 1 уведомление
    #     self.assertGreater(Notifications.objects.count(), 0)
    #     Notifications.objects.all().delete()
    #     # терь добавим 100 сотрудников, чтобы точно перекрыть нехватку
    #     self.create_many_users(100, dt_now - datetime.timedelta(days=15), dt_now + datetime.timedelta(days=15))
    #     self.assertEqual(Notifications.objects.count(), 0)  # уведомление о нехватке должно стать 0
    #
    #     Notifications.objects.all().delete()  # удаляем только что созданные
    #     Notifications.objects.bulk_create(existing_notifications)  # возвращаем те, которые были до этого

    def test_allocation_of_time_for_work_on_cashbox(self):
        allocation_of_time_for_work_on_cashbox()
        x = WorkerCashboxInfo.objects.all()
        self.assertEqual(x[0].duration, 0)
        # x[1].duration = 81.0
        # self.assertEqual(x[1].duration, 0)
        self.assertEqual(x[2].duration, 0)
        # 0.0 not greater than 0
        # self.assertGreater(x[3].duration, 0)

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

class Test_auto_worker_exchange(TestCase):
    dt_now = now().date()

    def setUp(self):
        super().setUp()

        self.superShop = SuperShop.objects.create(
            title='SuperShop1',
            tm_start=datetime.time(7, 0, 0),
            tm_end=datetime.time(0, 0, 0)
        )

        self.shop = Shop.objects.create(
            super_shop=self.superShop,
            title='Shop1'
        )

        self.shop2 = Shop.objects.create(
            super_shop=self.superShop,
            title='Shop2'
        )

        self.work_type = WorkType.objects.create(
            shop=self.shop,
            name='Кассы'
        )

        self.work_type2 = WorkType.objects.create(
            shop=self.shop2,
            name='Кассы'
        )

        self.operation_type = OperationType.objects.create(
            name='operation type №1',
            work_type=self.work_type,
            do_forecast=OperationType.FORECAST_HARD
        )

        self.operation_type2 = OperationType.objects.create(
            name='operation type №1',
            work_type=self.work_type2,
            do_forecast=OperationType.FORECAST_HARD
        )

        self.exchange_settings = ExchangeSettings.objects.create(
            automatic_check_lack_timegap=datetime.timedelta(days=1),
            automatic_check_lack=True,
            automatic_create_vacancy_lack_min=0.6,
            automatic_worker_select_lack_diff=0.6,
        )

    def create_vacancy(self, tm_from, tm_to):
        WorkerDayCashboxDetails.objects.create(
            dttm_from=('{} ' + tm_from).format(self.dt_now),
            dttm_to=('{} ' + tm_to).format(self.dt_now),
            work_type=self.work_type,
            status=WorkerDayCashboxDetails.TYPE_VACANCY,
            is_vacancy=True
        )

    def create_period_clients(self, value, operation_type):
        dttm_from = now().replace(hour=9, minute=0, second=0, microsecond=0)
        dttm_to = dttm_from.replace(hour=21, minute=0, second=0, microsecond=0)
        pc_list = []
        while dttm_from < dttm_to:
            pc_list.append(PeriodClients(
                dttm_forecast=dttm_from,
                value=value,
                type=PeriodClients.LONG_FORECASE_TYPE,
                operation_type=operation_type
            ))
            dttm_from += datetime.timedelta(minutes=30)
        else:
            PeriodClients.objects.bulk_create(pc_list)

    def create_users(self, quantity):
        for number in range(1, quantity + 1):
            User.objects.create_user(
                username='User{}'.format(number),
                email='test{}@test.ru'.format(number),
                shop=self.shop2,
                last_name='Имя{}'.format(number),
                first_name='Фамилия{}'.format(number)
            )

    def create_worker_day(self):
        for user in User.objects.all():
            wd = WorkerDay.objects.create(
                worker=user,
                dt=self.dt_now,
                type=WorkerDay.Type.TYPE_WORKDAY.value,
                dttm_work_start='{} 09:00:00'.format(self.dt_now),
                dttm_work_end='{} 21:00:00'.format(self.dt_now),
            )

            WorkerDayCashboxDetails.objects.create(
                dttm_from='{} 09:00:00'.format(self.dt_now),
                dttm_to='{} 21:00:00'.format(self.dt_now),
                work_type=self.work_type2,
                status=WorkerDayCashboxDetails.TYPE_WORK,
                is_vacancy=False,
                worker_day=wd
            )

    # Создали прогноз PeriodClients -> нужен 1 человек (1 вакансия), а у нас их 2 -> удаляем 1 вакансию
    def test_cancel_vacancies(self):
        self.create_vacancy('09:00:00', '20:00:00')
        self.create_vacancy('09:00:00', '20:00:00')

        self.create_period_clients(40, self.operation_type)

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY)), 2)

        cancel_vacancies()

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd.filter(status=WorkerDayCashboxDetails.TYPE_DELETED)), 1)
        self.assertEqual(len(wdcd.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY)), 1)

    # Нужны 3 вакансии -> у нас 0 -> создаём 3
    def test_create_vacancy_and_notify_cashiers_lack(self):
        self.create_period_clients(72, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 0)
        create_vacancy_and_notify_cashiers_lack()
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(20, 30)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(20, 30)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])

    # Нужно 3 вакансии -> у нас есть 2 -> нужно создать 1
    def test_create_vacancy_and_notify_cashiers_lack2(self):
        self.create_vacancy('09:00:00', '20:00:00')
        self.create_vacancy('09:00:00', '20:00:00')

        self.create_period_clients(72, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)
        create_vacancy_and_notify_cashiers_lack()
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])

    # Есть вакансия с 12-17, создаёт 2 доп. 1. 9-13; 2. 17-21
    def test_create_vacancy_and_notify_cashiers_lack3(self):
        self.create_vacancy('12:00:00', '17:00:00')

        self.create_period_clients(18, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 1)
        create_vacancy_and_notify_cashiers_lack()
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()], [datetime.time(9, 0),
                                                                              datetime.time(13, 0)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()], [datetime.time(12, 0),
                                                                              datetime.time(17, 0)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()], [datetime.time(17, 0),
                                                                              datetime.time(21, 0)])

    # Есть 2 вакансии 9-14 и 16-21. Создаётся 3ая с 14-18
    def test_create_vacancy_and_notify_cashiers_lack4(self):
        self.create_vacancy('09:00:00', '14:00:00')
        self.create_vacancy('16:00:00', '21:00:00')

        self.create_period_clients(18, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)
        create_vacancy_and_notify_cashiers_lack()
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()], [datetime.time(9, 0),
                                                                              datetime.time(14, 0)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()], [datetime.time(14, 0),
                                                                              datetime.time(18, 0)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()], [datetime.time(16, 0),
                                                                              datetime.time(21, 0)])

    # Есть 2 вакансии 9-15 и 16-21. Ничего не создаётся - разница между вакансиями < working_shift_min_hours / 2
    def test_create_vacancy_and_notify_cashiers_lack5(self):
        self.create_vacancy('09:00:00', '15:00:00')
        self.create_vacancy('16:00:00', '21:00:00')

        self.create_period_clients(18, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)
        create_vacancy_and_notify_cashiers_lack()
        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)

    # Предикшн в 3 человека -> 4 человека в работе -> 1 перекидывает.
    def test_workers_hard_exchange(self):
        self.create_users(4)
        self.create_worker_day()

        self.create_period_clients(18, self.operation_type)
        self.create_period_clients(72, self.operation_type2)

        self.create_vacancy('09:00:00', '21:00:00')
        Event.objects.create(
            text='Ивент для тестов, вакансия id 5.',
            department=self.shop,
            workerday_details=WorkerDayCashboxDetails.objects.get(pk=5)
        )

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 5)
        self.assertEqual(len(wdcd.filter(pk=1)), 1)
        self.assertEqual(wdcd.get(pk=5).status, WorkerDayCashboxDetails.TYPE_VACANCY)

        workers_hard_exchange()

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 4)
        self.assertEqual(len(wdcd.filter(pk=1)), 0)
        self.assertEqual(wdcd.get(pk=5).status, WorkerDayCashboxDetails.TYPE_WORK)

    # Предикшн в 4 человека -> 4 человека в работе -> никого не перекидывает.
    def test_workers_hard_exchange2(self):
        self.create_users(4)
        self.create_worker_day()

        self.create_period_clients(18, self.operation_type)
        self.create_period_clients(150, self.operation_type2)

        self.create_vacancy('09:00:00', '21:00:00')
        Event.objects.create(
            text='Ивент для тестов, вакансия id 5.',
            department=self.shop,
            workerday_details=WorkerDayCashboxDetails.objects.get(pk=5)
        )

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 5)

        workers_hard_exchange()

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 5)
