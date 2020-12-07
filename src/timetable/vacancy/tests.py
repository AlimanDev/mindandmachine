import datetime

from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils.timezone import now

from src.base.models import (
    Shop,
    Employment,
    User,
    Region,
    Event,
    ShopSettings,
    Network,
    Break,
)
from src.timetable.models import (
    WorkType,
    WorkTypeName,
    WorkerDay,
    WorkerDayCashboxDetails,
    ExchangeSettings,
    ShopMonthStat,
    EmploymentWorkType,
)

from src.forecast.models import (
    OperationType,
    PeriodClients,
    OperationTypeName,
)
from etc.scripts import fill_calendar
from src.timetable.vacancy.utils import (
    create_vacancies_and_notify,
    cancel_vacancies,
    workers_exchange,
    holiday_workers_exchange,
    worker_shift_elongation,
    confirm_vacancy,
)


class TestAutoWorkerExchange(TestCase):
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

        cls.work_type1 = WorkType.objects.create(
            shop=cls.shop,
            work_type_name=cls.work_type_name,
        )

        cls.work_type2 = WorkType.objects.create(
            shop=cls.shop2,
            work_type_name=cls.work_type_name,
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
            automatic_check_lack=True,
            automatic_exchange=True,
            automatic_create_vacancy_lack_min=0.4,
            automatic_delete_vacancy_lack_max=0.5,
            automatic_worker_select_overflow_min=0.6,
            automatic_worker_select_timegap=datetime.timedelta(hours=4),
            network=cls.network,
        )

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
            dttm_from += datetime.timedelta(minutes=30)
        else:
            PeriodClients.objects.bulk_create(pc_list)

    def create_users(self, quantity):
        for number in range(1, quantity + 1):
            user = User.objects.create_user(
                network=self.network,
                username='User{}'.format(number),
                email='test{}@test.ru'.format(number),
                last_name='Имя{}'.format(number),
                first_name='Фамилия{}'.format(number)
            )
            emp = Employment.objects.create(
                network=self.network,
                shop=self.shop2,
                user=user,
                dt_hired=self.dt_now - datetime.timedelta(days=1),
            )
            EmploymentWorkType.objects.create(
                employment=emp,
                work_type=self.work_type2,
            )

    def create_worker_day(self):
        for employment in Employment.objects.all():
            wd = WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
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

    def create_holidays(self, employment, dt_from, count):
        for day in range(count):
            date = dt_from + datetime.timedelta(days=day)
            WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
                shop=employment.shop,
                dt=date,
                type=WorkerDay.TYPE_HOLIDAY,
                is_approved=True,
            )

    def create_worker_days(self, employment, dt_from, count, from_tm, to_tm):
        for day in range(count):
            date = dt_from + datetime.timedelta(days=day)
            wd = WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
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

    # Создали прогноз PeriodClients -> нужен 1 человек (1 вакансия), а у нас их 2 -> удаляем 1 вакансию
    def test_cancel_vacancies(self):
        self.create_vacancy(9, 20, self.work_type1)
        self.create_vacancy(9, 20, self.work_type1)

        self.create_period_clients(1, self.operation_type)

        vacancies = WorkerDay.objects.filter(is_vacancy=True)
        self.assertEqual(vacancies.count(), 2)

        cancel_vacancies(self.shop.id, self.work_type1.id, approved=True)

        self.assertEqual(vacancies.count(), 1)

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

    # Нужно 3 вакансии -> у нас есть 2 -> нужно создать 1
    def test_create_vacancies_and_notify2(self):
        self.create_vacancy(9, 20, self.work_type1)
        self.create_vacancy(9, 20, self.work_type1)

        self.create_period_clients(3, self.operation_type)

        len_vacancies = len(WorkerDay.objects.filter(is_vacancy=True))
        self.assertEqual(len_vacancies, 2)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        vacancies = WorkerDay.objects.filter(is_vacancy=True).order_by('dttm_work_start')
        self.assertEqual([vacancies[0].dttm_work_start.time(), vacancies[0].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([vacancies[1].dttm_work_start.time(), vacancies[1].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([vacancies[2].dttm_work_start.time(), vacancies[2].dttm_work_end.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])

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

    # Предикшн в 3 человека -> 4 человека в работе -> 1 перекидывает.
    def test_workers_hard_exchange(self):
        self.create_users(4)
        if (now().hour >= 20):
            self.dt_now = self.dt_now + datetime.timedelta(days=1)
        self.create_worker_day()

        self.create_period_clients(1, self.operation_type)
        self.create_period_clients(3, self.operation_type2)

        vacancy = self.create_vacancy(9, 21, self.work_type1)
        Event.objects.create(
            type='vacancy',
            shop=self.shop,
            worker_day=vacancy,
        )

        worker_days = WorkerDay.objects.all()
        self.assertEqual(len(worker_days), 5)
        self.assertEqual(vacancy.is_vacancy, True)

        workers_exchange()

        worker_days = WorkerDay.objects.all()
        self.assertEqual(len(worker_days), 4)
        self.assertIsNotNone(worker_days.filter(is_vacancy=True).first().worker_id)

    # Предикшн в 4 человека -> 4 человека в работе -> никого не перекидывает.
    def test_workers_hard_exchange2(self):
        self.create_users(4)
        self.create_worker_day()

        self.create_period_clients(0, self.operation_type)
        self.create_period_clients(4, self.operation_type2)

        vacancy = self.create_vacancy(9, 21, self.work_type1)
        Event.objects.create(
            type='vacancy',
            shop=self.shop,
            worker_day=vacancy,
        )

        worker_days = WorkerDay.objects.all()
        self.assertEqual(len(worker_days), 5)

        workers_exchange()

        worker_days = WorkerDay.objects.all()
        self.assertEqual(len(worker_days), 5)
        self.assertIsNone(worker_days.filter(is_vacancy=True).first().worker_id)

    def test_workers_hard_exchange_holidays_3days(self):
        self.create_users(1)
        self.dt_now = self.dt_now + datetime.timedelta(days=8)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        employment = Employment.objects.first()
        dt = self.dt_now
        self.create_holidays(employment, dt, 3)
        self.create_worker_days(employment, dt + datetime.timedelta(days=4), 2, 2, 10)
        self.create_worker_days(employment, dt - datetime.timedelta(days=4), 2, 2, 10)
        Event.objects.create(
            worker_day=vacancy,
        )
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
        self.create_holidays(employment1, dt, 2)
        self.create_holidays(employment2, dt, 2)
        dt = dt + datetime.timedelta(days=2)
        self.create_worker_days(employment1, dt, 3, 10, 23)
        self.create_worker_days(employment2, dt, 3, 10, 18)
        dt = dt + datetime.timedelta(days=3)
        self.create_holidays(employment1, dt, 2)
        self.create_holidays(employment2, dt, 2)
        Event.objects.create(
            worker_day=vacancy,
        )
        holiday_workers_exchange()
        vacancy = WorkerDay.objects.get(is_vacancy=True)
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
        self.create_holidays(employment2, dt, 2)
        self.create_holidays(employment3, dt, 2)
        dt = dt + datetime.timedelta(days=1)
        self.create_holidays(employment1, dt, 2)
        dt = dt + datetime.timedelta(days=1)
        self.create_worker_days(employment2, dt, 3, 10, 18)
        self.create_worker_days(employment3, dt, 3, 9, 23)
        dt = dt + datetime.timedelta(days=1)
        self.create_worker_days(employment1, dt, 3, 10, 23)
        dt = dt + datetime.timedelta(days=2)
        self.create_holidays(employment2, dt, 2)
        self.create_holidays(employment3, dt, 2)
        dt = dt + datetime.timedelta(days=1)
        self.create_holidays(employment1, dt, 2)
        Event.objects.create(
            worker_day=vacancy,
        )
        holiday_workers_exchange()
        vacancy = WorkerDay.objects.get(is_vacancy=True)
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
        self.create_holidays(employment1, self.dt_now + datetime.timedelta(days=8), 2)
        self.create_worker_days(employment1, self.dt_now + datetime.timedelta(days=10), 3, 10, 23)
        self.create_holidays(employment1, self.dt_now + datetime.timedelta(days=13), 2)

        self.create_worker_days(employment2, self.dt_now + datetime.timedelta(days=4), 4, 10, 18)
        self.create_holidays(employment2, self.dt_now + datetime.timedelta(days=8), 1)
        self.create_worker_days(employment2, self.dt_now + datetime.timedelta(days=9), 3, 10, 18)
        self.create_holidays(employment3, self.dt_now + datetime.timedelta(days=12), 2)

        self.create_worker_days(employment3, self.dt_now + datetime.timedelta(days=4), 3, 8, 23)
        self.create_holidays(employment3, self.dt_now + datetime.timedelta(days=7), 2)
        self.create_worker_days(employment3, self.dt_now + datetime.timedelta(days=9), 3, 9, 23)
        self.create_holidays(employment3, self.dt_now + datetime.timedelta(days=12), 2)

        Event.objects.create(
            worker_day=vacancy,
        )
        holiday_workers_exchange()
        vacancy = WorkerDay.objects.get(is_vacancy=True)
        self.assertEqual(vacancy.employment, employment2)

    def test_worker_exchange_cant_apply_vacancy(self):
        self.create_users(1)
        user = User.objects.first()
        vacancy = self.create_vacancy(9, 21, self.work_type1)
        self.create_holidays(Employment.objects.get(user=user), self.dt_now, 1)
        tt = ShopMonthStat.objects.get(shop_id=self.shop.id)
        tt.dttm_status_change = self.dt_now + relativedelta(months=1)
        tt.save()
        Event.objects.create(
            worker_day=vacancy,
        )
        result = confirm_vacancy(vacancy.id, user)
        self.assertEqual(result, {'status_code': 400, 'code': 'cant_apply_vacancy'})

    def test_worker_exchange_change_vacancy_to_own_shop_vacancy(self):
        self.create_users(1)
        user = User.objects.first()
        vacancy = self.create_vacancy(9, 21, self.work_type1)
        self.create_holidays(Employment.objects.get(user=user), self.dt_now, 1)
        Event.objects.create(
            worker_day=vacancy,
        )
        confirm_vacancy(vacancy.id, user)
        vacancy = self.create_vacancy(9, 21, self.work_type2)
        Event.objects.create(
            worker_day=vacancy,
        )
        result = confirm_vacancy(vacancy.id, user)
        self.assertEqual(result, {'status_code': 200, 'code': 'vacancy_success'})

    def test_shift_elongation(self):
        self.create_users(1)
        user = User.objects.first()
        self.create_vacancy(9, 21, self.work_type2)
        self.create_worker_days(Employment.objects.get(user=user), self.dt_now, 1, 10, 18)
        worker_shift_elongation()
        wd = WorkerDay.objects.get(worker=user, is_approved=False)
        self.assertEqual(wd.dttm_work_start, datetime.datetime.combine(self.dt_now, datetime.time(9)))
        self.assertEqual(wd.dttm_work_end, datetime.datetime.combine(self.dt_now, datetime.time(21)))
