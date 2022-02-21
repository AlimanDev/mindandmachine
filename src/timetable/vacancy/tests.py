import datetime
import copy
from django.core import mail
from unittest import mock
from django.db import transaction

from django.test.utils import override_settings
from rest_framework.test import APITestCase
from src.celery.tasks import employee_not_checked
from src.recognition.events import EMPLOYEE_NOT_CHECKED_IN, EMPLOYEE_NOT_CHECKED_OUT
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.notifications.models.event_notification import EventEmailNotification
from src.timetable.events import EMPLOYEE_VACANCY_DELETED, VACANCY_CONFIRMED_TYPE, VACANCY_CREATED, VACANCY_DELETED, VACANCY_RECONFIRMED_TYPE, VACANCY_REFUSED

from dateutil.relativedelta import relativedelta
from django.utils.timezone import now

from etc.scripts import fill_calendar
from src.base.models import (
    Employee,
    FunctionGroup,
    Group,
    NetworkConnect,
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
    AttendanceRecords,
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
    cancel_vacancy,
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
        cls.network.set_settings_value(
            'shop_name_form', 
            {
                'singular': {
                    'I': 'подразделение',
                    'R': 'подразделения',
                    'P': 'подразделении',
                }
            }
        )
        cls.network.save()
        cls.breaks = Break.objects.create(network=cls.network, name='Default')
        cls.shop_settings = ShopSettings.objects.create(breaks=cls.breaks)
        Shop.objects.all().update(network=cls.network)

        cls.director_group = Group.objects.create(name='Director')
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
        cls.admin_group.subordinates.add(*Group.objects.all())
        
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

        cls.user_admin = User.objects.create_user(
            network=cls.network,
            username='admin',
            email='admin@test.ru',
            last_name='Admin',
            first_name='Admin',
        )
        cls.employee_admin = EmployeeFactory(user=cls.user_admin)
        cls.employment_admin = Employment.objects.create(
            shop=cls.root_shop,
            employee=cls.employee_admin,
            dt_hired=cls.dt_now - datetime.timedelta(days=2),
            function_group=cls.admin_group,
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
            shop=cls.shop,
            employee=cls.employee_dir,
            dt_hired=cls.dt_now - datetime.timedelta(days=2),
            function_group=cls.director_group,
        )

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
            shop_ancestors=True,
        )
        cls.event_email_notification_vacancy_created.shop_groups.add(cls.director_group)
        cls.event_email_notification_vacancy_deleted = EventEmailNotification.objects.create(
            event_type=cls.deleted_event,
            system_email_template='notifications/email/vacancy_deleted.html',
            subject='Автоматически удалена вакансия',
        )
        cls.event_email_notification_vacancy_deleted.shop_groups.add(cls.director_group)
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

        cls.operation_type = cls.work_type1.operation_type

        cls.operation_type2 = cls.work_type2.operation_type

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
        cls.employment_qs = Employment.objects.exclude(id__in=[cls.employment_dir.id, cls.employment_admin.id])

    def create_vacancy(self, tm_from, tm_to, work_type):
        wd = WorkerDay.objects.create(
            dttm_work_start=datetime.datetime.combine(self.dt_now, datetime.time(tm_from)),
            dttm_work_end=datetime.datetime.combine(self.dt_now, datetime.time(tm_to)),
            type_id=WorkerDay.TYPE_WORKDAY,
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
        for employment in self.employment_qs:
            wd = WorkerDay.objects.create(
                employment=employment,
                employee_id=employment.employee_id,
                shop=employment.shop,
                dt=self.dt_now,
                type_id=WorkerDay.TYPE_WORKDAY,
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
                    type_id=WorkerDay.TYPE_HOLIDAY,
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
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.datetime.combine(date, datetime.time(from_tm)),
                dttm_work_end=datetime.datetime.combine(date, datetime.time(to_tm)),
                is_approved=True,
            )

            WorkerDayCashboxDetails.objects.create(
                work_type=self.work_type2,
                worker_day=wd
            )

    def _assert_vacancy_created_notifications_created(self, assert_count):
        self.assertEqual(EventHistory.objects.filter(event_type=self.created_event).count(), assert_count)
        self.assertEqual(len(mail.outbox), assert_count)

    def _assert_vacancy_deleted_notifications_created(self, assert_count):
        self.assertEqual(EventHistory.objects.filter(event_type=self.deleted_event).count(), assert_count)
        self.assertEqual(len(mail.outbox), assert_count)

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
        vacancies = WorkerDay.objects.filter(is_vacancy=True, source=WorkerDay.SOURCE_AUTO_CREATED_VACANCY).order_by('dttm_work_start')
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
        self.assertEqual(len(worker_days), 4)  # TODO: скорее всего падает из-за переделок в confirm_vacancy, надо пофиксить
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
        self.dt_now = self.dt_now + datetime.timedelta(days=9)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employment = self.employment_qs.first()
        dt = self.dt_now
        self.update_or_create_holidays(employment, dt, 3)

        self.create_worker_days(employment, dt + datetime.timedelta(days=4), 2, 2, 10)
        self.create_worker_days(employment, dt - datetime.timedelta(days=4), 2, 2, 10)

        holiday_workers_exchange()

        self.assertIsNotNone(WorkerDay.objects.filter(employment=employment, is_vacancy=True).first())

    def test_workers_hard_exchange_holidays_2days_first(self):
        self.create_users(2)
        self.dt_now = self.dt_now + datetime.timedelta(days=9)
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
        self.dt_now = self.dt_now + datetime.timedelta(days=9)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employments = list(self.employment_qs)
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
        self.dt_now = self.dt_now + datetime.timedelta(days=9)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employments = list(self.employment_qs)
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
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employment, employment2)

    def test_worker_exchange_cant_apply_vacancy(self):
        self.create_users(1)
        user = User.objects.exclude(username__in=['dir', 'admin']).first()
        vacancy = self.create_vacancy(9, 21, self.work_type1)
        self.update_or_create_holidays(Employment.objects.get(employee__user=user), self.dt_now, 1)
        tt = ShopMonthStat.objects.get(shop_id=self.shop.id)
        tt.dttm_status_change = self.dt_now + relativedelta(months=1)
        tt.save()

        result = confirm_vacancy(vacancy.id, user)
        self.assertEqual(result, {'status_code': 400, 'text': 'Вы не можете выйти на эту смену.'})

    def test_worker_exchange_change_vacancy_to_own_shop_vacancy(self):
        self.create_users(1)
        user = User.objects.exclude(username__in=['dir', 'admin']).first()
        vacancy = self.create_vacancy(9, 21, self.work_type1)
        self.update_or_create_holidays(Employment.objects.get(employee__user=user), self.dt_now, 1)

        confirm_vacancy(vacancy.id, user)
        vacancy = self.create_vacancy(9, 21, self.work_type2)

        result = confirm_vacancy(vacancy.id, user)
        self.assertEqual(result, {'status_code': 200, 'text': 'Вакансия успешно принята.'})

    def test_shift_elongation(self):
        self.dt_now += datetime.timedelta(1)
        resp = self.create_users(1)
        user = resp[0][0]
        self.create_vacancy(9, 21, self.work_type2)
        self.create_worker_days(Employment.objects.get(employee__user=user), self.dt_now, 1, 10, 18)
        worker_shift_elongation()
        wd = WorkerDay.objects.get(employee__user=user, is_approved=False, source=WorkerDay.SOURCE_SHIFT_ELONGATION)  # FIXME: почему падает?
        self.assertEqual(wd.dttm_work_start, datetime.datetime.combine(self.dt_now, datetime.time(9)))
        self.assertEqual(wd.dttm_work_end, datetime.datetime.combine(self.dt_now, datetime.time(21)))

    def test_create_vacancy_notification(self):
        self.create_period_clients(1, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(mail.outbox[0].subject, self.event_email_notification_vacancy_created.subject)
        self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=21, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        work_type = self.work_type1.work_type_name.name
        self.assertEqual(
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
        self.assertEqual(mail.outbox[0].subject, self.event_email_notification_vacancy_deleted.subject)
        self.assertEqual(mail.outbox[0].to[0], self.user_dir.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=20, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        self.assertEqual(
            mail.outbox[0].body, 
            f'Здравствуйте, {self.user_dir.first_name}!\n\n\n\n\n\n\nВ подразделении {shop_name} отменена вакансия без сотрудника \n'
            f'Дата: {dt}\nВремя с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )

    def test_cancel_vacancy_notification_with_employee(self):
        self.create_users(2)
        self.dt_now = self.dt_now + datetime.timedelta(days=1)
        vac1 = self.create_vacancy(9, 20, self.work_type1)
        vac2 = self.create_vacancy(9, 20, self.work_type1)
        employments = list(self.employment_qs)
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
        wd = WorkerDay.objects.filter(employee_id=employments[0].employee_id, is_approved=True, source=WorkerDay.SOURCE_ON_CANCEL_VACANCY).first()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertFalse(wd.is_vacancy)
        self.assertEqual(vacancies.count(), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].subject, self.event_email_notification_employee_vacancy_deleted.subject)
        self.assertEqual(mail.outbox[0].to[0], employments[0].employee.user.email)
        self.assertEqual(mail.outbox[1].subject, self.event_email_notification_vacancy_deleted.subject)
        self.assertEqual(mail.outbox[1].to[0], self.user_dir.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=20, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        user = employments[0].employee.user
        user = f'{user.last_name} {user.first_name}'
        self.assertEqual(
            mail.outbox[0].body, 
            f'Здравствуйте, {employments[0].employee.user.first_name}!\n\n\n\n\n\n\nУ вас была автоматически отменена вакансия в подразделении {shop_name}.\n'
            f'Дата: {dt}\nВремя работы с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )
        self.assertEqual(
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
        self.assertEqual(len(worker_day.outsources.all()), 0)

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
        self.assertEqual(len(worker_day.outsources.all()), 2)

    def test_create_vacancy_on_approve(self):
        self.create_period_clients(1, self.operation_type)
        WorkerDay.objects.create(
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            employee=self.employee_dir,
            employment=self.employment_dir,
            shop=self.shop,
        )
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        self.client.force_authenticate(user=self.user_admin)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            data = {
                'shop_id': self.shop.id,
                'dt_from': self.dt_now,
                'dt_to': self.dt_now + datetime.timedelta(days=4),
                'is_fact': False,
            }
            response = self.client.post("/rest_api/worker_day/approve/", data, format='json')

            self.assertEqual(response.status_code, 200)
            vacancies = WorkerDay.objects.filter(is_vacancy=True).order_by('dttm_work_start')
            self.assertEqual([vacancies[0].dttm_work_start.time(), vacancies[0].dttm_work_end.time()],
                            [datetime.time(9, 0), datetime.time(21, 0)])
            
            self._assert_vacancy_created_notifications_created(1)

    def test_cancel_vacancy_and_create(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)

    def test_cancel_vacancy_and_create_with_employee(self):
        self.create_users(1)
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        employment = self.employment_qs.first()
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        vacancy.employee_id = employment.employee_id
        vacancy.employment = employment
        vacancy.save()
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        wd = WorkerDay.objects.filter(employee_id=employment.employee_id, is_approved=True).first()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_HOLIDAY)
        self.assertFalse(wd.is_vacancy)
        self.assertNotEqual(wd.id, vacancy.id)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(mail.outbox[2].subject, self.event_email_notification_employee_vacancy_deleted.subject)
        self.assertEqual(mail.outbox[2].to[0], employment.employee.user.email)
        shop_name = self.shop.name
        dt = self.dt_now
        dttm_from = datetime.datetime.combine(self.dt_now, datetime.time(9, 0))
        dttm_to = dttm_from.replace(hour=21, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
        dttm_from = dttm_from.strftime('%Y-%m-%d %H:%M:%S')
        user = employment.employee.user
        self.assertEqual(
            mail.outbox[2].body, 
            f'Здравствуйте, {user.first_name}!\n\n\n\n\n\n\nУ вас была отменена вакансия в подразделении {shop_name}.\n'
            f'Дата: {dt}\nВремя работы с {dttm_from} по {dttm_to}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)

    def test_cancel_vacancy_and_create_via_api(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
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
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['id'], vacancy.id)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.dttm_work_start, datetime.datetime.combine(self.dt_now, datetime.time(10, 0)))
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).count(), 0)

    def test_cancel_vacancy_and_create_via_api_another_work_type(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
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
        self.assertEqual(response.status_code, 201)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)

    def test_canceled_vacancy_not_showed(self):
        self.create_period_clients(2, self.operation_type)
        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        vacancy = WorkerDay.objects.filter(is_vacancy=True).first()
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_vacancy=True, canceled=True).first().id, vacancy.id)
        response = self.client.get(f'/rest_api/worker_day/vacancy/?limit=100&offset=0')
        self.assertEqual(len(response.json()['results']), 1)
        self.assertNotEqual(response.json()['results'][0]['id'], vacancy.id)

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

    def test_fact_vacancy_deleted(self):
        vacancy = WorkerDay.objects.create(
            is_fact=True,
            is_vacancy=True,
            employee=self.employee_dir,
            employment=self.employment_dir,
            dt=self.dt_now,
            dttm_work_start=datetime.datetime.combine(self.dt_now, datetime.time(8)),
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.delete(f"/rest_api/worker_day/{vacancy.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(WorkerDay.objects.filter(id=vacancy.id).first())


class TestVacancyActions(APITestCase, TestsHelperMixin):

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()


    def test_cancel_vacancy_without_worker(self):
        dt = datetime.date.today()
        approved_vacancy_auto = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
        )
        cancel_vacancy(approved_vacancy_auto.id, False)
        approved_vacancy_auto.refresh_from_db()
        self.assertIsNotNone(approved_vacancy_auto.id)
        self.assertTrue(approved_vacancy_auto.canceled)

        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            created_by=self.user1,
        )
        cancel_vacancy(approved_vacancy.id, False)
        self.assertIsNone(WorkerDay.objects.filter(id=approved_vacancy.id).first())

    def test_cancel_vacancy_with_worker_without_any_worker_days(self):
        dt = datetime.date.today()
        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        not_approved_vacancy = copy.deepcopy(approved_vacancy)
        not_approved_vacancy.id = None
        not_approved_vacancy.is_approved = False
        not_approved_vacancy.parent_worker_day_id = approved_vacancy.id
        not_approved_vacancy.save()
        cancel_vacancy(approved_vacancy.id, False)

        self.assertEqual(WorkerDay.objects.filter(id__in=[approved_vacancy.id, not_approved_vacancy.id]).count(), 0)
        self.assertTrue(WorkerDay.objects.filter(employee=self.employee1, type_id=WorkerDay.TYPE_HOLIDAY, is_approved=True).exists())
        self.assertTrue(WorkerDay.objects.filter(employee=self.employee1, type_id=WorkerDay.TYPE_HOLIDAY, is_approved=False).exists())
        WorkerDay.objects.filter(employee=self.employee1).delete()
        approved_vacancy.save()
        not_approved_vacancy.parent_worker_day = approved_vacancy
        not_approved_vacancy.save()

        cancel_vacancy(not_approved_vacancy.id, False)
        self.assertEqual(WorkerDay.objects.filter(id=not_approved_vacancy.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(id=approved_vacancy.id).count(), 1)
        self.assertTrue(WorkerDay.objects.filter(employee=self.employee1, type_id=WorkerDay.TYPE_HOLIDAY, is_approved=False).exists())
        self.assertFalse(WorkerDay.objects.filter(employee=self.employee1, type_id=WorkerDay.TYPE_HOLIDAY, is_approved=True).exists())

    def test_cancel_vacancy_with_worker_with_worker_days(self):
        dt = datetime.date.today()
        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(16)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        not_approved_vacancy = copy.deepcopy(approved_vacancy)
        not_approved_vacancy.id = None
        not_approved_vacancy.is_approved = False
        not_approved_vacancy.parent_worker_day_id = approved_vacancy.id
        not_approved_vacancy.save()
        approved_employee_worker_day = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(15)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        not_approved_employee_worker_day = copy.deepcopy(approved_employee_worker_day)
        not_approved_employee_worker_day.id = None
        not_approved_employee_worker_day.is_approved = False
        not_approved_employee_worker_day.parent_worker_day_id = approved_employee_worker_day.id
        not_approved_employee_worker_day.save()
        cancel_vacancy(approved_vacancy.id, False)

        self.assertEqual(WorkerDay.objects.filter(id__in=[approved_vacancy.id, not_approved_vacancy.id]).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=True, type_id=WorkerDay.TYPE_WORKDAY).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=False, type_id=WorkerDay.TYPE_WORKDAY).count(), 1)
        approved_vacancy.save()
        not_approved_vacancy.parent_worker_day_id = approved_vacancy.id
        not_approved_vacancy.save()

        cancel_vacancy(not_approved_vacancy.id, False)
        self.assertEqual(WorkerDay.objects.filter(id=not_approved_vacancy.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(id=approved_vacancy.id).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=True, type_id=WorkerDay.TYPE_WORKDAY).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=False, type_id=WorkerDay.TYPE_WORKDAY).count(), 1)

    def test_cancel_vacancy_with_worker_with_worker_days_only_approved(self):
        dt = datetime.date.today()
        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(16)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        not_approved_vacancy = copy.deepcopy(approved_vacancy)
        not_approved_vacancy.id = None
        not_approved_vacancy.is_approved = False
        not_approved_vacancy.parent_worker_day_id = approved_vacancy.id
        not_approved_vacancy.save()
        approved_employee_worker_day = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(15)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        cancel_vacancy(approved_vacancy.id, False)

        self.assertEqual(WorkerDay.objects.filter(id__in=[approved_vacancy.id, not_approved_vacancy.id]).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=True, type_id=WorkerDay.TYPE_WORKDAY).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=False, type_id=WorkerDay.TYPE_HOLIDAY).count(), 1)
        WorkerDay.objects.filter(employee=self.employee1, is_approved=False, type_id=WorkerDay.TYPE_HOLIDAY).delete()
        approved_vacancy.save()
        not_approved_vacancy.parent_worker_day_id = approved_vacancy.id
        not_approved_vacancy.save()

        cancel_vacancy(not_approved_vacancy.id, False)
        self.assertEqual(WorkerDay.objects.filter(id=not_approved_vacancy.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(id=approved_vacancy.id).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=True, type_id=WorkerDay.TYPE_WORKDAY).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=False, type_id=WorkerDay.TYPE_HOLIDAY).count(), 1)
    
    def test_cancel_vacancy_with_worker_with_worker_days_only_not_approved(self):
        dt = datetime.date.today()
        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(16)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        not_approved_vacancy = copy.deepcopy(approved_vacancy)
        not_approved_vacancy.id = None
        not_approved_vacancy.is_approved = False
        not_approved_vacancy.parent_worker_day_id = approved_vacancy.id
        not_approved_vacancy.save()
        not_approved_employee_worker_day = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=False,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(15)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        cancel_vacancy(approved_vacancy.id, False)

        self.assertEqual(WorkerDay.objects.filter(id__in=[approved_vacancy.id, not_approved_vacancy.id]).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=True, type_id=WorkerDay.TYPE_HOLIDAY).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=False, type_id=WorkerDay.TYPE_WORKDAY).count(), 1)
        WorkerDay.objects.filter(employee=self.employee1, is_approved=True, type_id=WorkerDay.TYPE_HOLIDAY).delete()
        approved_vacancy.save()
        not_approved_vacancy.parent_worker_day_id = approved_vacancy.id
        not_approved_vacancy.save()

        cancel_vacancy(not_approved_vacancy.id, False)
        self.assertEqual(WorkerDay.objects.filter(id=not_approved_vacancy.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(id=approved_vacancy.id).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=True, type_id=WorkerDay.TYPE_HOLIDAY).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(employee=self.employee1, is_approved=False, type_id=WorkerDay.TYPE_WORKDAY).count(), 1)

    def test_confirm_vacancy_from_holiday(self):
        dt = datetime.date.today()
        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
        )
        approved_employee_holiday = WorkerDay.objects.create(
            is_approved=True,
            dt=dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            employee=self.employee2,
            employment=self.employment2,
            created_by=self.user1,
        )
        not_approved_employee_holiday = copy.deepcopy(approved_employee_holiday)
        not_approved_employee_holiday.id = None
        not_approved_employee_holiday.is_approved = False
        not_approved_employee_holiday.parent_worker_day_id = approved_employee_holiday.id
        not_approved_employee_holiday.save()

        confirm_vacancy(approved_vacancy.id, self.user2, employee_id=self.employee2.id)

        self.assertEqual(WorkerDay.objects.filter(id=approved_employee_holiday.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(id=not_approved_employee_holiday.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(id=approved_vacancy.id, employee=self.employee2).count(), 1)
        wd = WorkerDay.objects.filter(employee=self.employee2, is_approved=False, type_id=WorkerDay.TYPE_WORKDAY, dt=approved_vacancy.dt).first()
        self.assertIsNotNone(wd)
        self.assertEqual(wd.parent_worker_day_id, approved_vacancy.id)

    def test_confirm_vacancy_from_holiday_when_not_approved_work_day(self):
        dt = datetime.date.today()
        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
        )
        approved_employee_holiday = WorkerDay.objects.create(
            is_approved=True,
            dt=dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            employee=self.employee2,
            employment=self.employment2,
            created_by=self.user1,
        )
        not_approved_employee_worker_day = copy.deepcopy(approved_employee_holiday)
        not_approved_employee_worker_day.id = None
        not_approved_employee_worker_day.is_approved = False
        not_approved_employee_worker_day.type_id = WorkerDay.TYPE_WORKDAY
        not_approved_employee_worker_day.dttm_work_start = datetime.datetime.combine(dt, datetime.time(14))
        not_approved_employee_worker_day.dttm_work_end = datetime.datetime.combine(dt, datetime.time(18))
        not_approved_employee_worker_day.parent_worker_day_id = approved_employee_holiday.id
        not_approved_employee_worker_day.save()

        confirm_vacancy(approved_vacancy.id, self.user2, employee_id=self.employee2.id)

        self.assertEqual(WorkerDay.objects.filter(id=approved_employee_holiday.id).count(), 0)
        self.assertEqual(WorkerDay.objects.filter(id=not_approved_employee_worker_day.id).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(id=approved_vacancy.id, employee=self.employee2).count(), 1)
        wd = WorkerDay.objects.filter(employee=self.employee2, is_approved=False, type_id=WorkerDay.TYPE_WORKDAY, dt=approved_vacancy.dt).first()
        self.assertIsNotNone(wd)
        self.assertIsNone(wd.parent_worker_day_id)

    def test_confirm_vacancy_with_other_vacancy_exists(self):
        dt = datetime.date.today()
        approved_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(16)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
        )
        approved_employee_worker_day = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(15)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            created_by=self.user1,
        )
        not_approved_employee_worker_day = copy.deepcopy(approved_employee_worker_day)
        not_approved_employee_worker_day.id = None
        not_approved_employee_worker_day.is_approved = False
        not_approved_employee_worker_day.parent_worker_day_id = approved_employee_worker_day.id
        not_approved_employee_worker_day.save()

        confirm_vacancy(approved_vacancy.id, self.user2, employee_id=self.employee2.id)

        self.assertEqual(WorkerDay.objects.filter(id=approved_employee_worker_day.id).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(id=not_approved_employee_worker_day.id).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(id=approved_vacancy.id, employee=self.employee2).count(), 1)
        self.assertEqual(
            WorkerDay.objects.filter(
                employee=self.employee2, 
                is_approved=False, 
                type_id=WorkerDay.TYPE_WORKDAY, 
                dt=approved_vacancy.dt, 
                parent_worker_day=approved_vacancy
            ).count(), 
            1,
        )

    def test_reconfirm_vacancy(self):
        dt = datetime.date.today()
        approved_employee1_vacancy = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, datetime.time(8)),
            dttm_work_end=datetime.datetime.combine(dt, datetime.time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            employee=self.employee1,
            employment=self.employment1,
            created_by=self.user1,
        )
        not_approved_employee1_vacancy = copy.deepcopy(approved_employee1_vacancy)
        not_approved_employee1_vacancy.id = None
        not_approved_employee1_vacancy.is_approved = False
        not_approved_employee1_vacancy.parent_worker_day_id = approved_employee1_vacancy.id
        not_approved_employee1_vacancy.save()
        approved_employee2_holiday = WorkerDay.objects.create(
            is_approved=True,
            dt=dt,
            type_id=WorkerDay.TYPE_HOLIDAY,
            employee=self.employee2,
            employment=self.employment2,
            created_by=self.user1,
        )
        not_approved_employee2_holiday = copy.deepcopy(approved_employee2_holiday)
        not_approved_employee2_holiday.id = None
        not_approved_employee2_holiday.is_approved = False
        not_approved_employee2_holiday.parent_worker_day_id = approved_employee2_holiday.id
        not_approved_employee2_holiday.save()

        confirm_vacancy(approved_employee1_vacancy.id, self.user1, employee_id=self.employee2.id, reconfirm=True)

        approved_employee1_vacancy.refresh_from_db()

        self.assertEqual(approved_employee1_vacancy.employee_id, self.employee2.id)
        self.assertEqual(approved_employee1_vacancy.employment_id, self.employment2.id)
        self.assertEqual(
            WorkerDay.objects.filter(
                id__in=[not_approved_employee1_vacancy.id, approved_employee2_holiday.id, not_approved_employee2_holiday.id]
            ).count(), 
            0,
        )
        self.assertTrue(
            WorkerDay.objects.filter(
                employee=self.employee1.id, 
                type_id=WorkerDay.TYPE_HOLIDAY, 
                dt=approved_employee1_vacancy.dt, 
                is_approved=True, 
                source=WorkerDay.SOURCE_ON_CANCEL_VACANCY
            ).exists()
        )
        self.assertTrue(
            WorkerDay.objects.filter(
                employee=self.employee1.id, 
                type_id=WorkerDay.TYPE_HOLIDAY, 
                dt=approved_employee1_vacancy.dt, 
                is_approved=False, 
                source=WorkerDay.SOURCE_ON_CANCEL_VACANCY
            ).exists()
        )
        self.assertTrue(
            WorkerDay.objects.filter(
                employee=self.employee2.id, 
                parent_worker_day_id=approved_employee1_vacancy.id, 
                type_id=WorkerDay.TYPE_WORKDAY, 
                is_approved=False, 
                source=WorkerDay.SOURCE_ON_CONFIRM_VACANCY
            ).exists()
        )

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestVacancyNotification(APITestCase, TestsHelperMixin):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.outsource_network1 = Network.objects.create(
            name='Outsource network 1',
        )
        cls.outsource_network2 = Network.objects.create(
            name='Outsource network 2',
        )
        NetworkConnect.objects.create(
            client=cls.network,
            outsourcing=cls.outsource_network1,
        )
        NetworkConnect.objects.create(
            client=cls.network,
            outsourcing=cls.outsource_network2,
        )
        cls.outsource_shop1 = Shop.objects.create(
            region=cls.region,
            network=cls.outsource_network1,
            name='Outsource shop 1',
        )
        cls.outsource_shop2 = Shop.objects.create(
            region=cls.region,
            network=cls.outsource_network2,
            name='Outsource shop 2',
        )
        create_users = [
            ('urs1', 'Urs', 'Urs1', cls.outsource_shop1, cls.admin_group),
            ('urs2', 'Urs', 'Urs2', cls.outsource_shop2, cls.admin_group),
            ('dir1', 'Dir', 'Dir1', cls.outsource_shop1, cls.chief_group),
            ('dir2', 'Dir', 'Dir2', cls.outsource_shop2, cls.chief_group),
            ('empl1', 'Empl', 'Empl1', cls.outsource_shop1, cls.employee_group),
            ('empl1_2', 'Empl', 'Empl1_2', cls.outsource_shop1, cls.employee_group),
            ('empl2', 'Empl', 'Empl2', cls.outsource_shop2, cls.employee_group),
        ]
        for user_data in create_users:
            user, employee, employment = cls._create_user(*user_data)
            setattr(cls, f'outsource_user_{user_data[0]}', user)
            setattr(cls, f'outsource_employee_{user_data[0]}', employee)
            setattr(cls, f'outsource_employment_{user_data[0]}', employment)
        
        cls.work_type_name = WorkTypeName.objects.create(
            name='Работа',
            network=cls.network,
        )
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop,
        )
        dt = datetime.date.today()
        ShopMonthStat.objects.bulk_create(
            [
                ShopMonthStat(
                    shop=shop,
                    dt=dt.replace(day=1),
                    dttm_status_change=datetime.datetime.now(),
                    is_approved=True,
                )
                for shop in Shop.objects.all()
            ]
        )

        cls.created_event, _ = EventType.objects.get_or_create(
            code=VACANCY_CREATED, network=cls.network,
        )
        cls.confirmed_event, _ = EventType.objects.get_or_create(
            code=VACANCY_CONFIRMED_TYPE, network=cls.network,
        )
        cls.reconfirmed_event, _ = EventType.objects.get_or_create(
            code=VACANCY_RECONFIRMED_TYPE, network=cls.network,
        )
        cls.refused_event, _ = EventType.objects.get_or_create(
            code=VACANCY_REFUSED, network=cls.network,
        )
        cls.delete_event, _ = EventType.objects.get_or_create(
            code=VACANCY_DELETED, network=cls.network,
        )
        cls.not_checked_in_event, _ = EventType.objects.get_or_create(
            code=EMPLOYEE_NOT_CHECKED_IN, network=cls.network,
        )
        cls.not_checked_out_event, _ = EventType.objects.get_or_create(
            code=EMPLOYEE_NOT_CHECKED_OUT, network=cls.network,
        )
        cls.employee_vacancy_deleted_event, _ = EventType.objects.get_or_create(
            code=EMPLOYEE_VACANCY_DELETED, network=cls.network,
        )
        cls.created_event_email_notification = cls._create_event_email_notification(
            cls.created_event, 'notifications/email/vacancy_created.html', 'Создана вакансия', users=[cls.outsource_user_urs1, cls.outsource_user_urs2], shop_groups=[cls.chief_group])
        cls.confirmed_event_email_notification = cls._create_event_email_notification(
            cls.confirmed_event, 'notifications/email/vacancy_confirmed.html', 'Сотрудник откликнулся на вакансию', shop_groups=[cls.chief_group])
        cls.reconfirmed_event_email_notification = cls._create_event_email_notification(
            cls.reconfirmed_event, 'notifications/email/vacancy_reconfirmed.html', 'Сотрудник переназначен на вакансию', shop_groups=[cls.chief_group])
        cls.refused_event_email_notification = cls._create_event_email_notification(
            cls.refused_event, 'notifications/email/vacancy_deleted.html', 'Отмена назначения сотрудника', 
            users=[cls.outsource_user_urs1, cls.outsource_user_urs2], employee_shop_groups=[cls.chief_group])
        cls.delete_event_email_notification = cls._create_event_email_notification(
            cls.delete_event, 'notifications/email/vacancy_deleted.html', 'Удалена вакансия', 
            users=[cls.outsource_user_urs1, cls.outsource_user_urs2], 
            employee_shop_groups=[cls.chief_group], shop_groups=[cls.chief_group])
        cls.not_checked_in_event_email_notification = cls._create_event_email_notification(
            cls.not_checked_in_event, 'notifications/email/employee_not_checked.html', 'Сотрудник не отметился на приход', users=[cls.outsource_user_urs1, cls.outsource_user_urs2],
            employee_shop_groups=[cls.chief_group], shop_groups=[cls.chief_group])
        cls.not_checked_out_event_email_notification = cls._create_event_email_notification(
            cls.not_checked_out_event, 'notifications/email/employee_not_checked.html', 'Сотрудник не отметился на уход', users=[cls.outsource_user_urs1, cls.outsource_user_urs2],
            employee_shop_groups=[cls.chief_group], shop_groups=[cls.chief_group])
        cls.employee_vacancy_deleted_event_email_notification = cls._create_event_email_notification(
            cls.employee_vacancy_deleted_event, 'notifications/email/employee_vacancy_deleted.html', 'Отменена вакансия', get_recipients_from_event_type=True)
        cls.dttm_format = '%Y-%m-%d %H:%M:%S'

    @classmethod
    def _create_event_email_notification(cls, event, system_email_template, subject, shop_groups=[], employee_shop_groups=[], users=[], get_recipients_from_event_type=False):
        notification = EventEmailNotification.objects.create(
            event_type=event,
            system_email_template=system_email_template,
            subject=subject,
            get_recipients_from_event_type=get_recipients_from_event_type,
        )
        notification.shop_groups.add(*shop_groups)
        notification.users.add(*users)
        notification.employee_shop_groups.add(*employee_shop_groups)
        return notification
    
    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user1)
    
    @classmethod
    def _create_user(cls, username, first_name, last_name, shop, function_group):
        user = User.objects.create(
            username=username,
            first_name=first_name,
            last_name=last_name,
            network_id=shop.network_id,
            email=f'{username}@test.com',
        )
        employee = Employee.objects.create(
            user=user,
            tabel_code=username,
        )
        employment = Employment.objects.create(
            employee=employee,
            shop=shop,
            function_group=function_group,
        )
        return user, employee, employment

    def test_vacancy_create_notification_sent(self):
        dt = datetime.date.today()
        dttm_work_start = datetime.datetime.combine(dt, datetime.time(10))
        dttm_work_end = datetime.datetime.combine(dt, datetime.time(20))
        response = self.client.post(
            '/rest_api/worker_day/',
            self.dump_data(
                {
                    'is_vacancy': True,
                    'is_outsource': True,
                    'shop_id': self.shop.id,
                    'dttm_work_start': dttm_work_start,
                    'dttm_work_end': dttm_work_end,
                    'type': WorkerDay.TYPE_WORKDAY,
                    'dt': dt,
                    'is_fact': False,
                    'worker_day_details': [
                        {
                            'work_type_id': self.work_type.id,
                            'work_part': 1.0,
                        }
                    ],
                    'outsources_ids': [
                        self.outsource_network1.id,
                    ]
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            response = self.client.post(
                '/rest_api/worker_day/approve/',
                self.dump_data(
                    {
                        'shop_id': self.shop.id,
                        'dt_from': dt,
                        'dt_to': dt,
                        'approve_open_vacs': True,
                        'is_fact': False,
                    }
                ),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        self.assertCountEqual([mail.outbox[0].to[0], mail.outbox[1].to[0]], [self.outsource_user_urs1.email, self.user6.email])
        body = ('Здравствуйте, {first_name}!\n\n\n\n\n\n\nВ магазине ' f'{self.shop.name} создана вакансия для типа работ Работа\n'
            f'Дата: {dt}\nВремя с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке')
        self.assertCountEqual(
            [mail.outbox[0].body, mail.outbox[1].body],
            [body.format(first_name=self.outsource_user_urs1.first_name), body.format(first_name=self.user6.first_name)],
        )

    def test_vacancy_confirmed_and_reconfirmed_notification_sent(self):
        dt = datetime.date.today()
        dttm_work_start = datetime.datetime.combine(dt, datetime.time(10))
        dttm_work_end = datetime.datetime.combine(dt, datetime.time(20))
        vacancy = WorkerDayFactory(
            cashbox_details__work_type=self.work_type,
            shop=self.shop,
            is_vacancy=True, 
            is_outsource=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_approved=True,
            employee=None,
            employment=None,
        )
        WorkerDayFactory(
            employee=self.outsource_employee_empl1,
            employment=self.outsource_employment_empl1,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt,
            is_approved=True,
        )
        WorkerDayFactory(
            employee=self.outsource_employee_empl1_2,
            employment=self.outsource_employment_empl1_2,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt,
            is_approved=True,
        )
        vacancy.outsources.add(self.outsource_network1)
        self.client.force_authenticate(user=self.outsource_user_urs1)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy.id}/confirm_vacancy_to_worker/',
            {
                'user_id': self.outsource_user_empl1.id,
                'employee_id': self.outsource_employee_empl1.id,
            }
        )
        self.assertEqual(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employee_id, self.outsource_employee_empl1.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to[0], self.user6.email)
        self.assertEqual(
            mail.outbox[0].body, 
            f'Здравствуйте, {self.user6.first_name}!\n\n\n\n\n\n\nАутсорс сотрудник {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name} откликнулся на вакансию с типом работ {self.work_type_name.name}\n'
            f'Дата: {vacancy.dt}\nМагазин: {self.shop.name}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
        )
        mail.outbox.clear()
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy.id}/reconfirm_vacancy_to_worker/',
            {
                'user_id': self.outsource_user_empl1_2.id,
                'employee_id': self.outsource_employee_empl1_2.id,
            }
        )
        self.assertEqual(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.employee_id, self.outsource_employee_empl1_2.id)
        self.assertEqual(len(mail.outbox), 4)
        self.assertCountEqual(
            list(map(lambda x: x.to[0], mail.outbox)), 
            [self.user6.email, self.outsource_user_dir1.email, self.outsource_user_empl1.email, self.outsource_user_urs1.email],
        )
        self.assertCountEqual(
            list(map(lambda x: x.body, mail.outbox)), 
            [
                f'Здравствуйте, {self.user6.first_name}!\n\n\n\n\n\n\nАутсорс сотрудник {self.outsource_user_empl1_2.last_name} {self.outsource_user_empl1_2.first_name} был назначен на вакансию с типом работ {self.work_type_name.name}'
                f', вместо аутсорс сотрудника {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name}\n'
                f'Дата: {vacancy.dt}\nМагазин: {self.shop.name}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке',
                f'Здравствуйте, {self.outsource_user_empl1.first_name}!\n\n\n\n\n\n\nУ вас была отменена вакансия в магазине {self.shop.name}.\n'
                f'Дата: {dt}\nВремя работы с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке',
                f'Здравствуйте, {self.outsource_user_dir1.first_name}!\n\n\n\n\n\n\nВ магазине {self.shop.name} отменена вакансия у сотрудника'
                f' {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name} с табельным номером {self.outsource_employee_empl1.tabel_code} \n'
                f'Дата: {dt}\nВремя с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке',
                f'Здравствуйте, {self.outsource_user_urs1.first_name}!\n\n\n\n\n\n\nВ магазине {self.shop.name} отменена вакансия у сотрудника'
                f' {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name} с табельным номером {self.outsource_employee_empl1.tabel_code} \n'
                f'Дата: {dt}\nВремя с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
            ]
        )

    def test_vacancy_refused_deleted_notification_sent(self):
        dt = datetime.date.today()
        dttm_work_start = datetime.datetime.combine(dt, datetime.time(10))
        dttm_work_end = datetime.datetime.combine(dt, datetime.time(20))
        vacancy = WorkerDayFactory(
            cashbox_details__work_type=self.work_type,
            shop=self.shop,
            is_vacancy=True, 
            is_outsource=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            is_approved=True,
            employee=self.outsource_employee_empl1,
            employment=self.outsource_employment_empl1,
            created_by=self.user1,
        )
        vacancy.outsources.add(self.outsource_network1)
        response = self.client.post(
            f'/rest_api/worker_day/{vacancy.id}/refuse_vacancy/',
        )
        self.assertEqual(response.status_code, 200)
        vacancy.refresh_from_db()
        self.assertIsNone(vacancy.employee_id)
        self.assertEqual(len(mail.outbox), 3)
        self.assertCountEqual(
            list(map(lambda x: x.to[0], mail.outbox)), 
            [self.outsource_user_dir1.email, self.outsource_user_empl1.email, self.outsource_user_urs1.email],
        )
        self.assertCountEqual(
            list(map(lambda x: x.body, mail.outbox)), 
            [
                f'Здравствуйте, {self.outsource_user_empl1.first_name}!\n\n\n\n\n\n\nУ вас была отменена вакансия в магазине {self.shop.name}.\n'
                f'Дата: {dt}\nВремя работы с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке',
                f'Здравствуйте, {self.outsource_user_dir1.first_name}!\n\n\n\n\n\n\nВ магазине {self.shop.name} отменена вакансия у сотрудника'
                f' {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name} с табельным номером {self.outsource_employee_empl1.tabel_code} \n'
                f'Дата: {dt}\nВремя с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке',
                f'Здравствуйте, {self.outsource_user_urs1.first_name}!\n\n\n\n\n\n\nВ магазине {self.shop.name} отменена вакансия у сотрудника'
                f' {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name} с табельным номером {self.outsource_employee_empl1.tabel_code} \n'
                f'Дата: {dt}\nВремя с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
            ]
        )
        mail.outbox.clear()
        vacancy.employee = self.outsource_employee_empl1
        vacancy.employment = self.outsource_employment_empl1
        vacancy.save()
        GroupWorkerDayPermission.objects.create(
            group=self.admin_group,
            worker_day_permission=WorkerDayPermission.objects.get(
                action=WorkerDayPermission.DELETE,
                graph_type=WorkerDayPermission.PLAN,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ),
            employee_type=GroupWorkerDayPermission.OUTSOURCE_NETWORK_EMPLOYEE,
            shop_type=GroupWorkerDayPermission.MY_NETWORK_SHOPS,
        )
        response = self.client.delete(
            f'/rest_api/worker_day/{vacancy.id}/',
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WorkerDay.objects.filter(pk=vacancy.id).exists())
        self.assertEqual(len(mail.outbox), 3)
        self.assertCountEqual(
            list(map(lambda x: x.to[0], mail.outbox)), 
            [self.outsource_user_dir1.email, self.outsource_user_empl1.email, self.outsource_user_urs1.email],
        )
        self.assertCountEqual(
            list(map(lambda x: x.body, mail.outbox)), 
            [
                f'Здравствуйте, {self.outsource_user_empl1.first_name}!\n\n\n\n\n\n\nУ вас была отменена вакансия в магазине {self.shop.name}.\n'
                f'Дата: {dt}\nВремя работы с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке',
                f'Здравствуйте, {self.outsource_user_dir1.first_name}!\n\n\n\n\n\n\nВ магазине {self.shop.name} отменена вакансия у сотрудника'
                f' {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name} с табельным номером {self.outsource_employee_empl1.tabel_code} \n'
                f'Дата: {dt}\nВремя с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке',
                f'Здравствуйте, {self.outsource_user_urs1.first_name}!\n\n\n\n\n\n\nВ магазине {self.shop.name} отменена вакансия у сотрудника'
                f' {self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name} с табельным номером {self.outsource_employee_empl1.tabel_code} \n'
                f'Дата: {dt}\nВремя с {dttm_work_start.strftime(self.dttm_format)} по {dttm_work_end.strftime(self.dttm_format)}\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке'
            ]
        )

    def test_employee_not_checked_notification_sent(self):
        self.maxDiff = None
        dt = datetime.date.today()
        dttm_now = datetime.datetime.now().replace(second=0) + datetime.timedelta(hours=self.shop.get_tz_offset())
        dttm_check = dttm_now - datetime.timedelta(minutes=5)
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            is_vacancy=True,
            is_outsource=True,
            employee=self.outsource_employee_empl1,
            employment=self.outsource_employment_empl1,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=dttm_check,
            dttm_work_end=dttm_now + datetime.timedelta(hours=6),
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            shop=self.shop,
            is_vacancy=True,
            is_outsource=True,
            employee=self.outsource_employee_empl1_2,
            employment=self.outsource_employment_empl1_2,
            dt=dt,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=dttm_now - datetime.timedelta(hours=6),
            dttm_work_end=dttm_check,
        )
        AttendanceRecords.objects.create(
            shop=self.shop,
            type=AttendanceRecords.TYPE_COMING,
            user=self.outsource_user_empl1_2,
            dttm=dttm_now - datetime.timedelta(hours=6, minutes=23)
        )
        employee_not_checked()

        self.assertEqual(len(mail.outbox), 6)
        self.assertCountEqual(
            list(map(lambda x: x.to[0], mail.outbox)), 
            [self.outsource_user_dir1.email, self.user6.email, self.outsource_user_urs1.email] * 2,
        )
        worker1 = f'{self.outsource_user_empl1.last_name} {self.outsource_user_empl1.first_name}'
        worker2 = f'{self.outsource_user_empl1_2.last_name} {self.outsource_user_empl1_2.first_name}'
        body = ('Здравствуйте, {first_name}!\n\n\n\n\n\n\nСотрудник {worker} не отметился на {type}.\n\n'
                'Время {shift_type} смены: {dttm}.\n\n' f'Магазин: {self.shop.name}.\n\n\n\n\n\n\nПисьмо отправлено роботом. Подробности можно узнать по ссылке')
        self.assertCountEqual(
            list(map(lambda x: x.body, mail.outbox)), 
            [
                body.format(first_name=self.outsource_user_dir1.first_name, worker=worker1, type='приход', shift_type='начала', dttm=dttm_check.strftime(self.dttm_format)),
                body.format(first_name=self.outsource_user_urs1.first_name, worker=worker1, type='приход', shift_type='начала', dttm=dttm_check.strftime(self.dttm_format)),
                body.format(first_name=self.user6.first_name, worker=worker1, type='приход', shift_type='начала', dttm=dttm_check.strftime(self.dttm_format)),
                body.format(first_name=self.outsource_user_dir1.first_name, worker=worker2, type='уход', shift_type='окончания', dttm=dttm_check.strftime(self.dttm_format)),
                body.format(first_name=self.outsource_user_urs1.first_name, worker=worker2, type='уход', shift_type='окончания', dttm=dttm_check.strftime(self.dttm_format)),
                body.format(first_name=self.user6.first_name, worker=worker2, type='уход', shift_type='окончания', dttm=dttm_check.strftime(self.dttm_format)),
            ]
        )
