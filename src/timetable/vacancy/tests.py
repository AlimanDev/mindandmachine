import datetime
from django.core import mail
from unittest import mock
from django.db import transaction

from django.test.utils import override_settings
from rest_framework.test import APITestCase
from src.notifications.models.event_notification import EventEmailNotification
from src.timetable.events import EMPLOYEE_VACANCY_DELETED, VACANCY_CREATED, VACANCY_DELETED

from dateutil.relativedelta import relativedelta
from django.utils.timezone import now

from etc.scripts import fill_calendar
from src.base.models import (
    FunctionGroup,
    Group,
    Shop,
    Employment,
    User,
    Region,
    ShopSettings,
    Network,
    Break,
)
from src.events.models import EventHistory, EventType
from src.base.tests.factories import (
    EmployeeFactory,
)
from src.forecast.models import (
    OperationType,
    PeriodClients,
    OperationTypeName,
)
from src.timetable.models import (
    GroupWorkerDayPermission,
    WorkType,
    WorkTypeName,
    WorkerDay,
    WorkerDayCashboxDetails,
    ExchangeSettings,
    ShopMonthStat,
    EmploymentWorkType,
    WorkerDayPermission,
)
from src.timetable.vacancy.utils import (
    create_vacancies_and_notify,
    cancel_vacancies,
    workers_exchange,
    holiday_workers_exchange,
    worker_shift_elongation,
    confirm_vacancy,
)

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestAutoWorkerExchange(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt_now = now().date()
        cls.region = Region.objects.create(
            name='Москва',
            code=77,
        )

        fill_calendar.main('2018.1.1', (datetime.datetime.now() + datetime.timedelta(days=365)).strftime('%Y.%m.%d'),
                           region_id=1)

        cls.network = Network.objects.create(
            primary_color='#BDF82',
            secondary_color='#390AC',
        )
        cls.breaks = Break.objects.create(network=cls.network, name='Default')
        cls.shop_settings = ShopSettings.objects.create(breaks=cls.breaks)
        Shop.objects.all().update(network=cls.network)

        cls.admin_group = Group.objects.create(name='ADMIN')
        FunctionGroup.objects.bulk_create([
            FunctionGroup(
                group=cls.admin_group,
                method=method,
                func=func,
                level_up=1,
                level_down=99,
                # access_type=FunctionGroup.TYPE_ALL
            ) for func, _ in FunctionGroup.FUNCS_TUPLE for method, _ in FunctionGroup.METHODS_TUPLE
        ])
        GroupWorkerDayPermission.objects.bulk_create(
            GroupWorkerDayPermission(
                group=cls.admin_group,
                worker_day_permission=wdp,
            ) for wdp in WorkerDayPermission.objects.all()
        )
        
        cls.root_shop = Shop.objects.create(
            name='SuperShop1',
            settings=cls.shop_settings,
            network=cls.network,
            tm_open_dict='{"all":"07:00:00"}',
            tm_close_dict='{"all":"23:00:00"}',
            region=cls.region,
        )

        cls.shop = Shop.objects.create(
            parent=cls.root_shop,
            name='Shop1',
            region=cls.region,
            settings=cls.shop_settings,
            network=cls.network,
            tm_open_dict='{"all":"07:00:00"}',
            tm_close_dict='{"all":"23:00:00"}',
        )

        cls.shop2 = Shop.objects.create(
            parent=cls.root_shop,
            name='Shop2',
            region=cls.region,
            settings=cls.shop_settings,
            network=cls.network,
            tm_open_dict='{"all":"07:00:00"}',
            tm_close_dict='{"all":"23:00:00"}',
        )

        cls.shop.exchange_shops.add(cls.shop)
        cls.shop.exchange_shops.add(cls.shop2)

        cls.shop3 = Shop.objects.create(
            parent=cls.root_shop,
            name='Shop3',
            region=cls.region,
            settings=cls.shop_settings,
            network=cls.network,
            tm_open_dict='{"all":"07:00:00"}',
            tm_close_dict='{"all":"23:00:00"}',
        )

        cls.shop.exchange_shops.add(cls.shop3)

        cls.shop4 = Shop.objects.create(
            parent=cls.root_shop,
            name='Shop4',
            region=cls.region,
            settings=cls.shop_settings,
            network=cls.network,
            tm_open_dict='{"all":"07:00:00"}',
            tm_close_dict='{"all":"23:00:00"}',
        )

        shops = [cls.shop, cls.shop2, cls.shop3, cls.shop4]
        for shop in shops:
            cls.shop2.exchange_shops.add(shop)
        dt = datetime.date.today()
        cls.timetables = ShopMonthStat.objects.bulk_create(
            [
                ShopMonthStat(
                    shop=shop,
                    dt=dt.replace(day=1),
                    dttm_status_change=datetime.datetime.now(),
                )
                for shop in shops
            ]
        )

        cls.work_type_name = WorkTypeName.objects.create(
            name='Кассы',
            code='',
            network=cls.network,
        )

        cls.work_type_name2 = WorkTypeName.objects.create(
            name='Кассы2',
            code='2',
            network=cls.network,
        )

        cls.user_dir = User.objects.create_user(
            network=cls.network,
            username='dir',
            email='dir@test.ru',
            last_name='Директор',
            first_name='Директор',
        )
        cls.employee_dir = EmployeeFactory(user=cls.user_dir)
        cls.employment_dir = Employment.objects.create(
            shop=cls.root_shop,
            employee=cls.employee_dir,
            dt_hired=cls.dt_now - datetime.timedelta(days=2),
            function_group=cls.admin_group,
        )

        cls.shop.director = cls.user_dir
        cls.shop.save()

        cls.created_event, _ = EventType.objects.get_or_create(
            code=VACANCY_CREATED, network=cls.network,
        )
        cls.deleted_event, _ = EventType.objects.get_or_create(
            code=VACANCY_DELETED, network=cls.network,
        )
        cls.employee_deleted_event, _ = EventType.objects.get_or_create(
            code=EMPLOYEE_VACANCY_DELETED, network=cls.network,
        )
        cls.event_email_notification_vacancy_created = EventEmailNotification.objects.create(
            event_type=cls.created_event,
            system_email_template='notifications/email/vacancy_created.html',
            subject='Автоматически создана вакансия',
            get_recipients_from_event_type=True,
        )
        cls.event_email_notification_vacancy_deleted = EventEmailNotification.objects.create(
            event_type=cls.deleted_event,
            system_email_template='notifications/email/vacancy_deleted.html',
            subject='Автоматически удалена вакансия',
            get_recipients_from_event_type=True,
        )
        cls.event_email_notification_employee_vacancy_deleted = EventEmailNotification.objects.create(
            event_type=cls.employee_deleted_event,
            system_email_template='notifications/email/employee_vacancy_deleted.html',
            subject='Удалена вакансия',
            get_recipients_from_event_type=True,
        )

        cls.work_type1 = WorkType.objects.create(
            shop=cls.shop,
            work_type_name=cls.work_type_name,
        )

        cls.work_type2 = WorkType.objects.create(
            shop=cls.shop2,
            work_type_name=cls.work_type_name,
        )

        cls.work_type3 = WorkType.objects.create(
            shop=cls.shop,
            work_type_name=cls.work_type_name2,
        )

        cls.operation_type_name = OperationTypeName.objects.create(
            name='',
            code='',
            network=cls.network,
            do_forecast=OperationTypeName.FORECAST,
        )

        cls.operation_type = OperationType.objects.create(
            operation_type_name=cls.operation_type_name,
            work_type=cls.work_type1,
        )

        cls.operation_type2 = OperationType.objects.create(
            operation_type_name=cls.operation_type_name,
            work_type=cls.work_type2,
        )

        cls.exchange_settings = ExchangeSettings.objects.create(
            automatic_check_lack_timegap=datetime.timedelta(days=1),
            automatic_create_vacancies=True,
            automatic_delete_vacancies=True,
            automatic_exchange=True,
            automatic_create_vacancy_lack_min=0.4,
            automatic_delete_vacancy_lack_max=0.5,
            automatic_worker_select_overflow_min=0.6,
            automatic_worker_select_timegap=datetime.timedelta(hours=4),
            network=cls.network,
        )

        cls.network.exchange_settings = cls.exchange_settings
        cls.network.save()

    def create_vacancy(self, tm_from, tm_to, work_type):
        wd = WorkerDay.objects.create(
            dttm_work_start=datetime.datetime.combine(self.dt_now, datetime.time(tm_from)),
            dttm_work_end=datetime.datetime.combine(self.dt_now, datetime.time(tm_to)),
            type=WorkerDay.TYPE_WORKDAY,
            is_vacancy=True,
            is_approved=True,
            dt=self.dt_now,
            shop=work_type.shop,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=wd,
            work_type=work_type,
        )
        return wd

    def create_period_clients(self, value, operation_type):
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=21, minute=0, second=0, microsecond=0)
        pc_list = []
        while dttm_from < dttm_to:
            pc_list.append(PeriodClients(
                dttm_forecast=dttm_from,
                value=value,
                type=PeriodClients.LONG_FORECASE_TYPE,
                operation_type=operation_type
            ))
            dttm_from += datetime.timedelta(minutes=60)
        else:
            PeriodClients.objects.bulk_create(pc_list)

    def create_users(self, quantity, user=None):
        resp = []
        for number in range(1, quantity + 1):
            new_user = user or User.objects.create_user(
                network=self.network,
                username='User{}'.format(number),
                email='test{}@test.ru'.format(number),
                last_name='Имя{}'.format(number),
                first_name='Фамилия{}'.format(number)
            )
            employee = EmployeeFactory(user=new_user)
            emp = Employment.objects.create(
                shop=self.shop2,
                employee=employee,
                dt_hired=self.dt_now - datetime.timedelta(days=2),
            )
            EmploymentWorkType.objects.create(
                employment=emp,
                work_type=self.work_type2,
            )
            resp.append((new_user, employee, emp))

        return resp

    def create_worker_day(self):
        for employment in Employment.objects.exclude(id=self.employment_dir.id):
            wd = WorkerDay.objects.create(
                employment=employment,
                employee_id=employment.employee_id,
                shop=employment.shop,
                dt=self.dt_now,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.datetime.combine(self.dt_now, datetime.time(9)),
                dttm_work_end=datetime.datetime.combine(self.dt_now, datetime.time(21)),
                is_approved=True,
            )

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type2,
                worker_day=wd
            )

    def update_or_create_holidays(self, employment, dt_from, count):
        for day in range(count):
            date = dt_from + datetime.timedelta(days=day)
            WorkerDay.objects.update_or_create(
                dt=date,
                employee_id=employment.employee_id,
                is_fact=False,
                is_approved=True,
                defaults=dict(
                    type=WorkerDay.TYPE_HOLIDAY,
                    shop=employment.shop,
                    employment=employment,
                )
            )

    def create_worker_days(self, employment, dt_from, count, from_tm, to_tm):
        for day in range(count):
            date = dt_from + datetime.timedelta(days=day)
            wd = WorkerDay.objects.create(
                employment=employment,
                employee_id=employment.employee_id,
                shop=employment.shop,
                dt=date,
                type=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.datetime.combine(date, datetime.time(from_tm)),
                dttm_work_end=datetime.datetime.combine(date, datetime.time(to_tm)),
                is_approved=True,
            )

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type2,
                worker_day=wd
            )

    def _assert_vacancy_created_notifications_created(self, assert_count):
        self.assertEquals(EventHistory.objects.filter(event_type=self.created_event).count(), assert_count)
        self.assertEquals(len(mail.outbox), assert_count)

    def _assert_vacancy_deleted_notifications_created(self, assert_count):
        self.assertEquals(EventHistory.objects.filter(event_type=self.deleted_event).count(), assert_count)
        self.assertEquals(len(mail.outbox), assert_count)

    # Создали прогноз PeriodClients -> нужен 1 человек (1 вакансия), а у нас их 2 -> удаляем 1 вакансию
    def test_cancel_vacancies(self):
        self.create_vacancy(9, 20, self.work_type1)
        self.create_vacancy(9, 20, self.work_type1)

        self.create_period_clients(1, self.operation_type)

        vacancies = WorkerDay.objects.filter(is_vacancy=True)
        self.assertEqual(vacancies.count(), 2)

        cancel_vacancies(self.shop.id, self.work_type1.id, approved=True)

        self.assertEqual(vacancies.count(), 1)
        self._assert_vacancy_deleted_notifications_created(1)

    # Нужны 3 вакансии -> у нас 0 -> создаём 3
    def test_create_vacancies_and_notify(self):
        self.create_period_clients(3, self.operation_type)

        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        vacancies = WorkerDay.objects.filter(is_vacancy=True).order_by('dttm_work_start')
        print(vacancies.count(), '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
        self.assertEqual([vacancies[0].dttm_work_start.time(), vacancies[0].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])
        self.assertEqual([vacancies[1].dttm_work_start.time(), vacancies[1].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])
        self.assertEqual([vacancies[2].dttm_work_start.time(), vacancies[2].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])
        self._assert_vacancy_created_notifications_created(3)
        
    # Нужно 3 вакансии -> у нас есть 2 -> нужно создать 1
    def test_create_vacancies_and_notify2(self):
        self.create_vacancy(9, 20, self.work_type1)
        self.create_vacancy(9, 20, self.work_type1)

        self.create_period_clients(3, self.operation_type)

        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 2)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        vacancies = WorkerDay.objects.filter(is_vacancy=True).order_by('dttm_work_start', 'dttm_work_end')
        self.assertEqual([vacancies[0].dttm_work_start.time(), vacancies[0].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([vacancies[1].dttm_work_start.time(), vacancies[1].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([vacancies[2].dttm_work_start.time(), vacancies[2].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])
        self._assert_vacancy_created_notifications_created(1)

    # Есть вакансия с 12-17, создаёт 2 доп. 1. 9-13; 2. 17-21
    def test_create_vacancies_and_notify3(self):
        self.create_vacancy(12, 17, self.work_type1)

        self.create_period_clients(1, self.operation_type)

        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 1)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        vacancies = WorkerDay.objects.filter(is_vacancy=True).order_by('dttm_work_start')
        self.assertEqual(
            [vacancies[0].dttm_work_start.time(), vacancies[0].dttm_work_end.time()],
            [datetime.time(9, 0), datetime.time(13, 0)]
        )
        self.assertEqual(
            [vacancies[1].dttm_work_start.time(), vacancies[1].dttm_work_end.time()],
            [datetime.time(12, 0), datetime.time(17, 0)]
        )
        self.assertEqual(
            [vacancies[2].dttm_work_start.time(), vacancies[2].dttm_work_end.time()],
            [datetime.time(17, 0), datetime.time(21, 0)]
        )
        self._assert_vacancy_created_notifications_created(2)

    # Есть 2 вакансии 9-14 и 16-21. Создаётся 3ая с 14-18
    def test_create_vacancies_and_notify4(self):
        self.create_vacancy(9, 14, self.work_type1)
        self.create_vacancy(16, 21, self.work_type1)

        self.create_period_clients(1, self.operation_type)

        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 2)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        vacancies = WorkerDay.objects.filter(is_vacancy=True).order_by('dttm_work_start')
        self.assertEqual(
            [vacancies[0].dttm_work_start.time(), vacancies[0].dttm_work_end.time()],
            [datetime.time(9, 0), datetime.time(14, 0)]
        )
        self.assertEqual(
            [vacancies[1].dttm_work_start.time(), vacancies[1].dttm_work_end.time()],
            [datetime.time(14, 0), datetime.time(18, 0)]
        )
        self.assertEqual(
            [vacancies[2].dttm_work_start.time(), vacancies[2].dttm_work_end.time()],
            [datetime.time(16, 0), datetime.time(21, 0)]
        )
        self._assert_vacancy_created_notifications_created(1)

    # Есть 2 вакансии 9-15 и 16-21. Ничего не создаётся - разница между вакансиями < working_shift_min_hours / 2
    def test_create_vacancies_and_notify5(self):
        self.create_vacancy(9, 15, self.work_type1)
        self.create_vacancy(16, 21, self.work_type1)

        self.create_period_clients(1, self.operation_type)

        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 2)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 2)
        self._assert_vacancy_created_notifications_created(0)

    # Предикшн в 3 человека -> 4 человека в работе -> 1 перекидывает.
    def test_workers_hard_exchange(self):
        self.create_users(4)
        if (now().hour >= 20):
            self.dt_now = self.dt_now + datetime.timedelta(days=1)
        self.create_worker_day()

        self.create_period_clients(1, self.operation_type)
        self.create_period_clients(3, self.operation_type2)

        vacancy = self.create_vacancy(9, 21, self.work_type1)

        worker_days = WorkerDay.objects.all()
        self.assertEqual(len(worker_days), 5)
        self.assertEqual(vacancy.is_vacancy, True)

        workers_exchange()

        worker_days = WorkerDay.objects.filter(is_approved=True)
        self.assertEqual(len(worker_days), 4)
        self.assertIsNotNone(worker_days.filter(is_vacancy=True).first().employee_id)

    # Предикшн в 4 человека -> 4 человека в работе -> никого не перекидывает.
    def test_workers_hard_exchange2(self):
        self.create_users(4)
        self.create_worker_day()

        self.create_period_clients(0, self.operation_type)
        self.create_period_clients(4, self.operation_type2)

        vacancy = self.create_vacancy(9, 21, self.work_type1)

        worker_days = WorkerDay.objects.all()
        self.assertEqual(len(worker_days), 5)

        workers_exchange()

        worker_days = WorkerDay.objects.all()
        self.assertEqual(len(worker_days), 5)
        self.assertIsNone(worker_days.filter(is_vacancy=True).first().employee_id)

    def test_workers_hard_exchange_holidays_3days(self):
        self.create_users(1)
        self.dt_now = self.dt_now + datetime.timedelta(days=8)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employment = Employment.objects.exclude(pk=self.employment_dir.id).first()
        dt = self.dt_now
        self.update_or_create_holidays(employment, dt, 3)

        self.create_worker_days(employment, dt + datetime.timedelta(days=4), 2, 2, 10)
        self.create_worker_days(employment, dt - datetime.timedelta(days=4), 2, 2, 10)

        holiday_workers_exchange()

        self.assertIsNotNone(WorkerDay.objects.filter(employment=employment, is_vacancy=True).first())

    def test_workers_hard_exchange_holidays_2days_first(self):
        self.create_users(2)
        self.dt_now = self.dt_now + datetime.timedelta(days=8)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employment1 = Employment.objects.first()
        employment2 = Employment.objects.last()
        dt = self.dt_now - datetime.timedelta(days=4)
        self.create_worker_days(employment1, dt, 4, 10, 23)
        self.create_worker_days(employment2, dt, 4, 10, 18)
        dt = dt + datetime.timedelta(days=4)
        self.update_or_create_holidays(employment1, dt, 2)
        self.update_or_create_holidays(employment2, dt, 2)
        dt = dt + datetime.timedelta(days=2)
        self.create_worker_days(employment1, dt, 3, 10, 23)
        self.create_worker_days(employment2, dt, 3, 10, 18)
        dt = dt + datetime.timedelta(days=3)
        self.update_or_create_holidays(employment1, dt, 2)
        self.update_or_create_holidays(employment2, dt, 2)

        holiday_workers_exchange()
        vacancy = WorkerDay.objects.get(is_vacancy=True, is_approved=True)
        self.assertEqual(vacancy.employment, employment2)

    def test_workers_hard_exchange_holidays_2days_last(self):
        self.create_users(3)
        self.dt_now = self.dt_now + datetime.timedelta(days=8)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employments = list(Employment.objects.all())
        employment1 = employments[0]
        employment2 = employments[1]
        employment3 = employments[2]
        dt = self.dt_now - datetime.timedelta(days=4)
        self.create_worker_days(employment1, dt, 4, 10, 23)
        self.create_worker_days(employment2, dt, 3, 10, 18)
        self.create_worker_days(employment3, dt, 3, 10, 20)
        dt = dt + datetime.timedelta(days=3)
        self.update_or_create_holidays(employment2, dt, 2)
        self.update_or_create_holidays(employment3, dt, 2)
        dt = dt + datetime.timedelta(days=1)
        self.update_or_create_holidays(employment1, dt, 2)
        dt = dt + datetime.timedelta(days=1)
        self.create_worker_days(employment2, dt, 3, 10, 18)
        self.create_worker_days(employment3, dt, 3, 9, 23)
        dt = dt + datetime.timedelta(days=1)
        self.create_worker_days(employment1, dt, 3, 10, 23)
        dt = dt + datetime.timedelta(days=2)
        self.update_or_create_holidays(employment2, dt, 2)
        self.update_or_create_holidays(employment3, dt, 2)
        dt = dt + datetime.timedelta(days=1)
        self.update_or_create_holidays(employment1, dt, 2)

        holiday_workers_exchange()
        vacancy = WorkerDay.objects.get(is_vacancy=True, is_approved=True)
        self.assertEqual(vacancy.employment, employment2)

    def test_workers_hard_exchange_holidays_1day(self):
        self.create_users(3)
        self.dt_now = self.dt_now + datetime.timedelta(days=8)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employments = list(Employment.objects.all())
        employment1 = employments[0]
        employment2 = employments[1]
        employment3 = employments[2]
        self.dt_now = self.dt_now - datetime.timedelta(days=8)
        self.create_worker_days(employment1, self.dt_now + datetime.timedelta(days=4), 4, 10, 23)
        self.update_or_create_holidays(employment1, self.dt_now + datetime.timedelta(days=8), 2)
        self.create_worker_days(employment1, self.dt_now + datetime.timedelta(days=10), 3, 10, 23)
        self.update_or_create_holidays(employment1, self.dt_now + datetime.timedelta(days=13), 2)

        self.create_worker_days(employment2, self.dt_now + datetime.timedelta(days=4), 4, 10, 18)
        self.update_or_create_holidays(employment2, self.dt_now + datetime.timedelta(days=8), 1)
        self.create_worker_days(employment2, self.dt_now + datetime.timedelta(days=9), 3, 10, 18)
        self.update_or_create_holidays(employment3, self.dt_now + datetime.timedelta(days=12), 2)

        self.create_worker_days(employment3, self.dt_now + datetime.timedelta(days=4), 3, 8, 23)
        self.update_or_create_holidays(employment3, self.dt_now + datetime.timedelta(days=7), 2)
        self.create_worker_days(employment3, self.dt_now + datetime.timedelta(days=9), 3, 9, 23)
        self.update_or_create_holidays(employment3, self.dt_now + datetime.timedelta(days=12), 2)

        holiday_workers_exchange()
        vacancy = WorkerDay.objects.get(is_vacancy=True, is_approved=True)
        self.assertEqual(vacancy.employment, employment2)

    def test_worker_exchange_cant_apply_vacancy(self):
        self.create_users(1)
        user = User.objects.exclude(username='dir').first()
        vacancy = self.create_vacancy(9, 21, self.work_type1)
        self.update_or_create_holidays(Employment.objects.get(employee__user=user), self.dt_now, 1)
        tt = ShopMonthStat.objects.get(shop_id=self.shop.id)
        tt.dttm_status_change = self.dt_now + relativedelta(months=1)
        tt.save()

        result = confirm_vacancy(vacancy.id, user)
        self.assertEqual(result, {'status_code': 400, 'text': 'Вы не можете выйти на эту смену.'})

    def test_worker_exchange_change_vacancy_to_own_shop_vacancy(self):
        self.create_users(1)
        user = User.objects.exclude(username='dir').first()
        vacancy = self.create_vacancy(9, 21, self.work_type1)
        self.update_or_create_holidays(Employment.objects.get(employee__user=user), self.dt_now, 1)

        confirm_vacancy(vacancy.id, user)
        vacancy = self.create_vacancy(9, 21, self.work_type2)

        result = confirm_vacancy(vacancy.id, user)
        self.assertEqual(result, {'status_code': 200, 'text': 'Вакансия успешно принята.'})

    def test_shift_elongation(self):
        resp = self.create_users(1)
        user = resp[0][0]
        self.create_vacancy(9, 21, self.work_type2)
        self.create_worker_days(Employment.objects.get(employee__user=user), self.dt_now, 1, 10, 18)
        worker_shift_elongation()
        wd = WorkerDay.objects.get(employee__user=user, is_approved=False)  # FIXME: почему падает?
        self.assertEqual(wd.dttm_work_start, datetime.datetime.combine(self.dt_now, datetime.time(9)))
        self.assertEqual(wd.dttm_work_end, datetime.datetime.combine(self.dt_now, datetime.time(21)))

    def test_create_vacancy_notification(self):
        self.create_period_clients(1, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(mail.outbox[0].subject, self.event_email_notification_vacancy_created.subject)
        self.assertEquals(mail.outbox[0].to[0], self.user_dir.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=21, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        work_type = self.work_type1.work_type_name.name
        self.assertEquals(
            mail.outbox[0].body, 
            f'Здравствуйте, {self.user_dir.first_name}!\n\n\n\n\n\n\nВ подразделении {shop_name} автоматически создана вакансия для типа работ {work_type}\n'
            f'Дата: {dt}\nВремя с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )

    def test_cancel_vacancy_notification_without_employee(self):
        self.create_vacancy(9, 20, self.work_type1)
        self.create_vacancy(9, 20, self.work_type1)
        self.create_period_clients(1, self.operation_type)
        vacancies = WorkerDay.objects.filter(is_vacancy=True)
        self.assertEqual(vacancies.count(), 2)
        cancel_vacancies(self.shop.id, self.work_type1.id, approved=True)
        self.assertEqual(vacancies.count(), 1)
        self.assertEquals(mail.outbox[0].subject, self.event_email_notification_vacancy_deleted.subject)
        self.assertEquals(mail.outbox[0].to[0], self.user_dir.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=20, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        self.assertEquals(
            mail.outbox[0].body, 
            f'Здравствуйте, {self.user_dir.first_name}!\n\n\n\n\n\n\nВ подразделении {shop_name} отменена вакансия без сотрудника \n'
            f'Дата: {dt}\nВремя с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )

    def test_cancel_vacancy_notification_with_employee(self):
        self.create_users(2)
        self.dt_now = self.dt_now + datetime.timedelta(days=1)
        vac1 = self.create_vacancy(9, 20, self.work_type1)
        vac2 = self.create_vacancy(9, 20, self.work_type1)
        employments = list(Employment.objects.exclude(id=self.employment_dir.id))
        vac1.employee_id = employments[0].employee_id
        vac1.employment = employments[0]
        vac1.save()
        vac2.employee_id = employments[1].employee_id
        vac2.employment = employments[1]
        vac2.save()
        self.create_period_clients(1, self.operation_type)
        vacancies = WorkerDay.objects.filter(is_vacancy=True)
        self.assertEqual(vacancies.count(), 2)
        cancel_vacancies(self.shop.id, self.work_type1.id, approved=True)
        wd = WorkerDay.objects.filter(employee_id=employments[0].employee_id, is_approved=True).first()
        self.assertEquals(wd.type, WorkerDay.TYPE_HOLIDAY)
        self.assertFalse(wd.is_vacancy)
        self.assertEqual(vacancies.count(), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEquals(mail.outbox[0].subject, self.event_email_notification_employee_vacancy_deleted.subject)
        self.assertEquals(mail.outbox[0].to[0], employments[0].employee.user.email)
        self.assertEquals(mail.outbox[1].subject, self.event_email_notification_vacancy_deleted.subject)
        self.assertEquals(mail.outbox[1].to[0], self.user_dir.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=20, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        user = employments[0].employee.user
        user = f'{user.last_name} {user.first_name}'
        self.assertEquals(
            mail.outbox[0].body, 
            f'Здравствуйте, {employments[0].employee.user.first_name}!\n\n\n\n\n\n\nУ вас была автоматически отменена вакансия в подразделении {shop_name}.\n'
            f'Дата: {dt}\nВремя работы с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )
        self.assertEquals(
            mail.outbox[1].body, 
            f'Здравствуйте, {self.user_dir.first_name}!\n\n\n\n\n\n\nВ подразделении {shop_name} отменена вакансия у сотрудника {user} без табельного номера \n'
            f'Дата: {dt}\nВремя с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )

    def test_create_vacancy_without_outsource(self):
        self.create_period_clients(1, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        worker_day = WorkerDay.objects.filter(is_vacancy=True).first()
        self.assertFalse(worker_day.is_outsource)
        self.assertEquals(len(worker_day.outsources.all()), 0)

    def test_create_vacancy_with_outsource(self):
        network_outource1 = Network.objects.create(
            name='Outsource Network'
        )
        network_outource2 = Network.objects.create(
            name='Outsource Network2'
        )
        self.exchange_settings.outsources.add(network_outource1, network_outource2)
        self.create_period_clients(1, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        worker_day = WorkerDay.objects.filter(is_vacancy=True).first()
        self.assertTrue(worker_day.is_outsource)
        self.assertEquals(len(worker_day.outsources.all()), 2)

    def test_create_vacancy_on_approve(self):
        self.create_period_clients(1, self.operation_type)
        WorkerDay.objects.create(
            type=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            employee=self.employee_dir,
            employment=self.employment_dir,
            shop=self.shop,
        )
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        self.client.force_authenticate(user=self.user_dir)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            data = {
                'shop_id': self.shop.id,
                'dt_from': self.dt_now,
                'dt_to': self.dt_now + datetime.timedelta(days=4),
                'is_fact': False,
            }
            response = self.client.post("/rest_api/worker_day/approve/", data, format='json')

            self.assertEquals(response.status_code, 200)
            vacancies = WorkerDay.objects.filter(is_vacancy=True).order_by('dttm_work_start')
            self.assertEqual([vacancies[0].dttm_work_start.time(), vacancies[0].dttm_work_end.time()],
                            [datetime.time(9, 0), datetime.time(21, 0)])
            
            self._assert_vacancy_created_notifications_created(1)

    def test_cancel_vacancy_and_create(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_dir)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEquals(response.status_code, 204)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)

    def test_cancel_vacancy_and_create_with_employee(self):
        self.create_users(1)
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        employment = Employment.objects.exclude(id=self.employment_dir.id).first()
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        vacancy.employee_id = employment.employee_id
        vacancy.employment = employment
        vacancy.save()
        self.client.force_authenticate(user=self.user_dir)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEquals(response.status_code, 204)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        wd = WorkerDay.objects.filter(employee_id=employment.employee_id, is_approved=True).first()
        self.assertEquals(wd.type, WorkerDay.TYPE_HOLIDAY)
        self.assertFalse(wd.is_vacancy)
        self.assertNotEquals(wd.id, vacancy.id)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEquals(mail.outbox[2].subject, self.event_email_notification_employee_vacancy_deleted.subject)
        self.assertEquals(mail.outbox[2].to[0], employment.employee.user.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=21, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        user = employment.employee.user
        self.assertEquals(
            mail.outbox[2].body, 
            f'Здравствуйте, {user.first_name}!\n\n\n\n\n\n\nУ вас была отменена вакансия в подразделении {shop_name}.\n'
            f'Дата: {dt}\nВремя работы с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)

    def test_cancel_vacancy_and_create_via_api(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_dir)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEquals(response.status_code, 204)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        response = self.client.post(
            '/rest_api/worker_day/',
            data={
                'shop_id': self.shop.id,
                'is_vacancy': True,
                'type': WorkerDay.TYPE_WORKDAY,
                'worker_day_details': [
                    {
                        'work_part': 1.0,
                        'work_type_id': self.work_type1.id,
                    },
                ],
                'dttm_work_start': datetime.datetime.combine(self.dt_now, datetime.time(10, 0)),
                'dttm_work_end': datetime.datetime.combine(self.dt_now, datetime.time(21, 0)),
                'dt': self.dt_now,
                'is_fact': False,
            },
            format='json'
        )
        self.assertEquals(response.status_code, 201)
        self.assertEquals(response.json()['id'], vacancy.id)
        vacancy.refresh_from_db()
        self.assertEquals(vacancy.dttm_work_start, datetime.datetime.combine(self.dt_now, datetime.time(10, 0)))
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).count(), 0)

    def test_cancel_vacancy_and_create_via_api_another_work_type(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_dir)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEquals(response.status_code, 204)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        response = self.client.post(
            '/rest_api/worker_day/',
            data={
                'shop_id': self.shop.id,
                'is_vacancy': True,
                'type': WorkerDay.TYPE_WORKDAY,
                'worker_day_details': [
                    {
                        'work_part': 1.0,
                        'work_type_id': self.work_type3.id,
                    },
                ],
                'dttm_work_start': datetime.datetime.combine(self.dt_now, datetime.time(9, 0)),
                'dttm_work_end': datetime.datetime.combine(self.dt_now, datetime.time(21, 0)),
                'dt': self.dt_now,
                'is_fact': False,
            },
            format='json'
        )
        self.assertEquals(response.status_code, 201)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 3)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)

    def test_canceled_vacancy_not_showed(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_dir)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEquals(response.status_code, 204)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEquals(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        response = self.client.get(f'/rest_api/worker_day/vacancy/?limit=100&offset=0')
        self.assertEquals(len(response.json()['results']), 1)
        self.assertNotEquals(response.json()['results'][0]['id'], vacancy.id)

    def test_employees_time_overlap_on_confirm_vacancies(self):
        resp = self.create_users(1)
        user, employee1, employment1 = resp[0]
        self.update_or_create_holidays(employment1, self.dt_now, 1)
        resp2 = self.create_users(1, user=user)
        _user, employee2, employment2 = resp2[0]
        self.update_or_create_holidays(employment2, self.dt_now, 1)
        vac1 = self.create_vacancy(9, 21, self.work_type2)
        vac2 = self.create_vacancy(9, 21, self.work_type2)
        result = confirm_vacancy(vac1.id, user, employee_id=employee1.id)
        self.assertDictEqual(result, {'status_code': 200, 'text': 'Вакансия успешно принята.'})
        result = confirm_vacancy(vac2.id, user, employee_id=employee2.id)
        self.assertEqual(result['status_code'], 400)
        self.assertIn('Операция не может быть выполнена. Недопустимое пересечение времени работы.', result['text'])
