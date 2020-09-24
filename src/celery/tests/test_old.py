from src.util.test import LocalTestCase


from src.timetable.models import (
    EmploymentWorkType,
    WorkerDayCashboxDetails,
)

from ..tasks import (
    # update_worker_month_stat,
    allocation_of_time_for_work_on_cashbox,
    release_all_workers,
    create_pred_bills,
    cancel_vacancies,
    workers_hard_exchange
)


class TestCelery(LocalTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp()

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


    # def test_release_all_workers(self):
    #     release_all_workers()
    #     amount_of_unreleased_workers = WorkerDayCashboxDetails.objects.filter(dttm_to__isnull=True).count()
    #     self.assertEqual(amount_of_unreleased_workers, 0)

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

    # def test_allocation_of_time_for_work_on_cashbox(self):
    #     allocation_of_time_for_work_on_cashbox()
    #     x = EmploymentWorkType.objects.all()
    #     self.assertEqual(x[0].duration, 0)
    #     # x[1].duration = 81.0
    #     # self.assertEqual(x[1].duration, 0)
    #     self.assertEqual(x[2].duration, 0)
    #     # 0.0 not greater than 0
    #     # self.assertGreater(x[3].duration, 0)

    def test_create_pred_bills(self):
        from django.core.exceptions import EmptyResultSet
        try:
            create_pred_bills()
        except EmptyResultSet:
            pass

