import datetime

from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.utils.timezone import now

from src.base.models import (
    Shop,
    Employment,
    User,
    Region,
)
from src.timetable.models import (
    WorkType,
    WorkerDay,
    WorkerDayCashboxDetails,
    ExchangeSettings,
    Event,
)

from src.forecast.models import (
    OperationType,
    PeriodClients,
)
from etc.scripts import fill_calendar
from src.util.test import LocalTestCase
from .utils import create_vacancies_and_notify, cancel_vacancies, workers_exchange


class TestWorkerExchange(LocalTestCase):
    dttm_now = now()
    dttm = (dttm_now - relativedelta(days=15)).replace(hour=6, minute=30, second=0, microsecond=0)
    qos_dt = dttm.strftime('%d.%m.%Y')

    def setUp(self):
        super().setUp(worker_day=False)
        self.exchange_settings = ExchangeSettings.objects.create(
            automatic_check_lack_timegap=datetime.timedelta(days=1),
            automatic_check_lack=True,
            automatic_create_vacancy_lack_min=0.4,
            automatic_delete_vacancy_lack_max=0.5,
            automatic_worker_select_overflow_min=0.6,
            automatic_worker_select_timegap=datetime.timedelta(hours=4)
        )

    def test_get_workers_to_exchange(self):
        self.auth()

        user = self.user3
        employment = self.employment3
        employment.is_ready_for_overworkings = True
        employment.save()

        wd_dttm_from = (self.dttm - relativedelta(days=5)).replace(hour=9, minute=0,)
        wd_dttm_to = (self.dttm - relativedelta(days=5)).replace(hour=18, minute=0,)

        worker_day = WorkerDay.objects.create(
            worker=user,
            employment=employment,
            shop=self.shop,
            type=WorkerDay.TYPE_WORKDAY,
            dt=wd_dttm_from.date(),
            dttm_work_start=wd_dttm_from,
            dttm_work_end=wd_dttm_to,
        )

        WorkerDayCashboxDetails.objects.create(
            worker_day=worker_day,
            work_type=self.work_type3,
            dttm_from=worker_day.dttm_work_start,
            dttm_to=worker_day.dttm_work_end,
        )

        response = self.api_get(
            '/api/timetable/worker_exchange/get_workers_to_exchange?specialization=2&dttm_start=09:00:00 {0}&dttm_end=18:00:00 {0}'.format(
                self.qos_dt))


        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(response.json()['data']['users']['3']['info'], {
            'id': 3,
            'username': 'user3',
            # 'shop_id': self.shop.id,
            'first_name': 'Иван3',
            'last_name': 'Сидоров',
            'middle_name': None,
            'avatar_url': None,
            'sex': 'F',
            'phone_number': None,
            'email': 'u3@b.b',
            # 'tabel_code': None,
            # 'shop_title': 'Shop1',
            # 'supershop_title': 'Region Shop1',
        })

        self.assertEqual(len(response.json()['data']['users']['3']['timetable']), 1)
        self.assertEqual(response.json()['data']['tt_from_dt'],
                         (self.dttm - relativedelta(days=10)).strftime('%d.%m.%Y'))
        self.assertEqual(response.json()['data']['tt_to_dt'], (self.dttm + relativedelta(days=10)).strftime('%d.%m.%Y'))

    def test_notify_workers_about_vacancy(self):
        self.auth()

        response = self.api_post('/api/timetable/worker_exchange/notify_workers_about_vacancy',
                                 {'work_type': 2, 'dttm_start': '09:00:00 {}'.format(self.qos_dt),
                                  'dttm_end': '15:00:00 {}'.format(self.qos_dt)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        response = self.api_post('/api/timetable/worker_exchange/notify_workers_about_vacancy',
                                 {'work_type': 2, 'dttm_start': '15:00:00 {}'.format(self.qos_dt),
                                  'dttm_end': '21:00:00 {}'.format(self.qos_dt)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        vacancy = WorkerDayCashboxDetails.objects.filter(is_vacancy=True).order_by('id')
        wt = WorkType.objects.get(pk=2)

        self.assertEqual(vacancy[0].dttm_from, self.dttm.replace(hour=9, minute=0, second=0, microsecond=0))
        self.assertEqual(vacancy[0].dttm_to, self.dttm.replace(hour=15, minute=0, second=0, microsecond=0))
        self.assertEqual(vacancy[0].work_type, wt)

        self.assertEqual(vacancy[1].dttm_from, self.dttm.replace(hour=15, minute=0, second=0, microsecond=0))
        self.assertEqual(vacancy[1].dttm_to, self.dttm.replace(hour=21, minute=0, second=0, microsecond=0))
        self.assertEqual(vacancy[1].work_type, wt)

    def test_show_vacancy(self):
        self.auth()

        response = self.api_get(
            '/api/timetable/worker_exchange/show_vacancy?shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(response.json()['data']['vacancies'], [])

        wt = WorkType.objects.get(
            shop=self.shop, name='Тип_кассы_2')
        WorkerDayCashboxDetails.objects.create(
            dttm_from='{} 09:00:00'.format(self.dttm.date()),
            dttm_to='{} 15:00:00'.format(self.dttm.date()),
            work_type=wt,
            status=WorkerDayCashboxDetails.TYPE_VACANCY,
            is_vacancy=True,
        )
        WorkerDayCashboxDetails.objects.create(
            dttm_from='{} 15:00:00'.format(self.dttm.date()),
            dttm_to='{} 21:00:00'.format(self.dttm.date()),
            work_type=wt,
            status=WorkerDayCashboxDetails.TYPE_VACANCY,
            is_vacancy=True,
        )

        response = self.api_get(
            '/api/timetable/worker_exchange/show_vacancy?shop_id={}'.format(
                self.shop.id
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        self.assertEqual(response.json()['data']['vacancies'][0]['dt'], self.qos_dt)
        self.assertEqual(response.json()['data']['vacancies'][0]['dttm_from'], '15:00:00')
        self.assertEqual(response.json()['data']['vacancies'][0]['dttm_to'], '21:00:00')
        self.assertEqual(response.json()['data']['vacancies'][0]['worker_fio'], '')
        self.assertEqual(response.json()['data']['vacancies'][0]['is_canceled'], False)
        self.assertEqual(response.json()['data']['vacancies'][0]['work_type'], 2)
        self.assertEqual(response.json()['data']['vacancies'][1]['dt'], self.qos_dt)
        self.assertEqual(response.json()['data']['vacancies'][1]['dttm_from'], '09:00:00')
        self.assertEqual(response.json()['data']['vacancies'][1]['dttm_to'], '15:00:00')
        self.assertEqual(response.json()['data']['vacancies'][1]['worker_fio'], '')
        self.assertEqual(response.json()['data']['vacancies'][1]['is_canceled'], False)
        self.assertEqual(response.json()['data']['vacancies'][1]['work_type'], 2)

    def test_cancel_vacancy(self):
        self.auth()

        wt = WorkType.objects.get(
            shop=self.shop, name='Тип_кассы_2')
        worker_day_detail = WorkerDayCashboxDetails.objects.create(
            dttm_from='{} 09:00:00'.format(self.dttm.date()),
            dttm_to='{} 15:00:00'.format(self.dttm.date()),
            work_type=wt,
            status=WorkerDayCashboxDetails.TYPE_VACANCY,
            is_vacancy=True,
        )
        worker_day_detail2 = WorkerDayCashboxDetails.objects.create(
            dttm_from='{} 15:00:00'.format(self.dttm.date()),
            dttm_to='{} 21:00:00'.format(self.dttm.date()),
            work_type=wt,
            status=WorkerDayCashboxDetails.TYPE_VACANCY,
            is_vacancy=True,
        )

        response = self.api_post('/api/timetable/worker_exchange/cancel_vacancy',
                                 {'vacancy_id': worker_day_detail.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(type(WorkerDayCashboxDetails.objects.get(pk=worker_day_detail.id).dttm_deleted),
                         type(datetime.datetime.now()))
        self.assertEqual(WorkerDayCashboxDetails.objects.get(pk=worker_day_detail2.id).dttm_deleted, None)


class Test_auto_worker_exchange(TestCase):
    dt_now = now().date()

    def setUp(self):
        super().setUp()

        self.region = Region.objects.create(
            id=1,
            name='Москва',
            code=77,
        )

        fill_calendar.main('2018.1.1', '2019.1.1', region_id=1)


        self.root_shop = Shop.objects.create(
            title='SuperShop1',
            tm_shop_opens=datetime.time(7, 0, 0),
            tm_shop_closes=datetime.time(0, 0, 0)
        )

        self.shop = Shop.objects.create(
            parent=self.root_shop,
            title='Shop1',
            region=self.region,
        )

        self.shop2 = Shop.objects.create(
            parent=self.root_shop,
            title='Shop2',
            region=self.region,
        )

        self.work_type1 = WorkType.objects.create(
            shop=self.shop,
            name='Кассы'
        )

        self.work_type2 = WorkType.objects.create(
            shop=self.shop2,
            name='Кассы'
        )

        self.operation_type = OperationType.objects.create(
            name='operation type №1',
            work_type=self.work_type1,
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
            automatic_create_vacancy_lack_min=0.4,
            automatic_delete_vacancy_lack_max=0.5,
            automatic_worker_select_overflow_min=0.6,
            automatic_worker_select_timegap=datetime.timedelta(hours=4)
        )

    def create_vacancy(self, tm_from, tm_to):
        return WorkerDayCashboxDetails.objects.create(
            dttm_from=('{} ' + tm_from).format(self.dt_now),
            dttm_to=('{} ' + tm_to).format(self.dt_now),
            work_type=self.work_type1,
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
            user=User.objects.create_user(
                username='User{}'.format(number),
                email='test{}@test.ru'.format(number),
                last_name='Имя{}'.format(number),
                first_name='Фамилия{}'.format(number)
            )
            Employment.objects.create(
                shop = self.shop2,
                user=user
            )

    def create_worker_day(self):
        for employment in Employment.objects.all():
            wd = WorkerDay.objects.create(
                employment=employment,
                worker=employment.user,
                shop=employment.shop,
                dt=self.dt_now,
                type=WorkerDay.TYPE_WORKDAY,
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

        cancel_vacancies(self.shop.id, self.work_type1.id)

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd.filter(status=WorkerDayCashboxDetails.TYPE_DELETED)), 1)
        self.assertEqual(len(wdcd.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY)), 1)

    # Нужны 3 вакансии -> у нас 0 -> создаём 3
    def test_create_vacancies_and_notify(self):
        self.create_period_clients(72, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 0)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        print(wdcd.count(), '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])

    # Нужно 3 вакансии -> у нас есть 2 -> нужно создать 1
    def test_create_vacancies_and_notify2(self):
        self.create_vacancy('09:00:00', '20:00:00')
        self.create_vacancy('09:00:00', '20:00:00')

        self.create_period_clients(72, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(20, 0)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()],
                         [datetime.time(9, 0), datetime.time(21, 0)])

    # Есть вакансия с 12-17, создаёт 2 доп. 1. 9-13; 2. 17-21
    def test_create_vacancies_and_notify3(self):
        self.create_vacancy('12:00:00', '17:00:00')

        self.create_period_clients(18, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 1)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()], [datetime.time(9, 0),
                                                                              datetime.time(13, 0)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()], [datetime.time(12, 0),
                                                                              datetime.time(17, 0)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()], [datetime.time(17, 0),
                                                                              datetime.time(21, 0)])

    # Есть 2 вакансии 9-14 и 16-21. Создаётся 3ая с 14-18
    def test_create_vacancies_and_notify4(self):
        self.create_vacancy('09:00:00', '14:00:00')
        self.create_vacancy('16:00:00', '21:00:00')

        self.create_period_clients(18, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        wdcd = WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY).order_by('dttm_to')
        self.assertEqual([wdcd[0].dttm_from.time(), wdcd[0].dttm_to.time()], [datetime.time(9, 0),
                                                                              datetime.time(14, 0)])
        self.assertEqual([wdcd[1].dttm_from.time(), wdcd[1].dttm_to.time()], [datetime.time(14, 0),
                                                                              datetime.time(18, 0)])
        self.assertEqual([wdcd[2].dttm_from.time(), wdcd[2].dttm_to.time()], [datetime.time(16, 0),
                                                                              datetime.time(21, 0)])

    # Есть 2 вакансии 9-15 и 16-21. Ничего не создаётся - разница между вакансиями < working_shift_min_hours / 2
    def test_create_vacancies_and_notify5(self):
        self.create_vacancy('09:00:00', '15:00:00')
        self.create_vacancy('16:00:00', '21:00:00')

        self.create_period_clients(18, self.operation_type)

        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)
        create_vacancies_and_notify(self.shop.id, self.work_type1.id)
        len_wdcd = len(WorkerDayCashboxDetails.objects.filter(status=WorkerDayCashboxDetails.TYPE_VACANCY))
        self.assertEqual(len_wdcd, 2)

    # Предикшн в 3 человека -> 4 человека в работе -> 1 перекидывает.
    def test_workers_hard_exchange(self):
        self.create_users(4)
        self.create_worker_day()

        self.create_period_clients(18, self.operation_type)
        self.create_period_clients(72, self.operation_type2)

        vacancy=self.create_vacancy('09:00:00', '21:00:00')
        Event.objects.create(
            text='Ивент для тестов, вакансия id 5.',
            department=self.shop,
            workerday_details=vacancy
        )

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 5)
        # self.assertEqual(len(wdcd.filter(pk=1)), 1)
        self.assertEqual(vacancy.status, WorkerDayCashboxDetails.TYPE_VACANCY)

        workers_exchange()

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 4)
        # self.assertEqual(len(wdcd.filter(pk=1)), 0)
        self.assertEqual(wdcd.get(pk=vacancy.id).status, WorkerDayCashboxDetails.TYPE_WORK)
    # Предикшн в 4 человека -> 4 человека в работе -> никого не перекидывает.
    def test_workers_hard_exchange2(self):
        self.create_users(4)
        self.create_worker_day()

        self.create_period_clients(18, self.operation_type)
        self.create_period_clients(150, self.operation_type2)

        vacancy=self.create_vacancy('09:00:00', '21:00:00')
        Event.objects.create(
            text='Ивент для тестов, вакансия id 5.',
            department=self.shop,
            workerday_details=vacancy
        )

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 5)

        workers_exchange()

        wdcd = WorkerDayCashboxDetails.objects.all()
        self.assertEqual(len(wdcd), 5)
