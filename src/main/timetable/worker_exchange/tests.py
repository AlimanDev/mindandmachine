from src.util.test import LocalTestCase
from src.db.models import (
    WorkType,
    WorkerDayCashboxDetails,
    Shop,
    User,
    WorkerDay,
)
import datetime
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta


class TestWorkerExchange(LocalTestCase):
    dttm_now = now()
    dttm = (dttm_now - relativedelta(days=15)).replace(hour=6, minute=30, second=0, microsecond=0)
    qos_dt = dttm.strftime('%d.%m.%Y')

    def setUp(self):
        super().setUp()

    def test_get_workers_to_exchange(self):
        self.auth()

        user = User.objects.filter(workercashboxinfo__work_type=WorkType.objects.get(pk=2))[0]
        user.is_ready_for_overworkings = True
        user.save()
        wd = WorkerDay.objects.filter(worker=user)[0]
        wd.type = 1
        wd.save()

        response = self.api_get(
            '/api/timetable/worker_exchange/get_workers_to_exchange?own_shop=True&specialization=2&dttm_start=09:00:00 {0}&dttm_end=21:00:00 {0}'.format(
                self.qos_dt))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['users']['3']['info'], {
            'id': 3,
            'username': 'user3',
            'shop_id': 1,
            'first_name': 'Иван3',
            'last_name': 'Сидоров',
            'middle_name': None,
            'avatar_url': None,
            'sex': 'F',
            'phone_number': None,
            'email': '',
            'tabel_code': None,
            'shop_title': 'Shop1',
            'supershop_title': 'SuperShop1',
        })
        self.assertEqual(len(response.json['data']['users']['3']['timetable']), 11)
        self.assertEqual(response.json['data']['tt_from_dt'], (self.dttm - relativedelta(days=10)).strftime('%d.%m.%Y'))
        self.assertEqual(response.json['data']['tt_to_dt'], (self.dttm + relativedelta(days=10)).strftime('%d.%m.%Y'))

    def test_notify_workers_about_vacancy(self):
        self.auth()

        response = self.api_post('/api/timetable/worker_exchange/notify_workers_about_vacancy',
                                 {'work_type': 2, 'dttm_start': '09:00:00 {}'.format(self.qos_dt),
                                  'dttm_end': '15:00:00 {}'.format(self.qos_dt)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        response = self.api_post('/api/timetable/worker_exchange/notify_workers_about_vacancy',
                                 {'work_type': 2, 'dttm_start': '15:00:00 {}'.format(self.qos_dt),
                                  'dttm_end': '21:00:00 {}'.format(self.qos_dt)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

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
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['vacancies'], [])

        wt = WorkType.objects.get(shop=Shop.objects.get(pk=1), name='Тип_кассы_2')
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
            '/api/timetable/worker_exchange/show_vacancy?shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        self.assertEqual(response.json['data']['vacancies'][0]['dt'], self.qos_dt)
        self.assertEqual(response.json['data']['vacancies'][0]['dttm_from'], '15:00:00')
        self.assertEqual(response.json['data']['vacancies'][0]['dttm_to'], '21:00:00')
        self.assertEqual(response.json['data']['vacancies'][0]['worker_fio'], '')
        self.assertEqual(response.json['data']['vacancies'][0]['is_canceled'], False)
        self.assertEqual(response.json['data']['vacancies'][0]['work_type'], 2)
        self.assertEqual(response.json['data']['vacancies'][1]['dt'], self.qos_dt)
        self.assertEqual(response.json['data']['vacancies'][1]['dttm_from'], '09:00:00')
        self.assertEqual(response.json['data']['vacancies'][1]['dttm_to'], '15:00:00')
        self.assertEqual(response.json['data']['vacancies'][1]['worker_fio'], '')
        self.assertEqual(response.json['data']['vacancies'][1]['is_canceled'], False)
        self.assertEqual(response.json['data']['vacancies'][1]['work_type'], 2)

    def test_cancel_vacancy(self):
        self.auth()

        wt = WorkType.objects.get(shop=Shop.objects.get(pk=1), name='Тип_кассы_2')
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
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(type(WorkerDayCashboxDetails.objects.get(pk=worker_day_detail.id).dttm_deleted),
                         type(datetime.datetime.now()))
        self.assertEqual(WorkerDayCashboxDetails.objects.get(pk=worker_day_detail2.id).dttm_deleted, None)
