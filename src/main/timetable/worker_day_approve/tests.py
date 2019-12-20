from src.util.test import LocalTestCase
from src.timetable.models import WorkerDayApprove
from dateutil.relativedelta import relativedelta
from django.utils.timezone import now


class TestAutoSettings(LocalTestCase):

    def setUp(self):
        self.dt = now().replace(day=1).date()
        self.dt2 = now().replace(day=1).date()- relativedelta(months=1)
        super().setUp()

    def test_worker_day_approve(self):
        self.auth()

        response = self.api_post(
            '/api/timetable/worker_day_approve/create_worker_day_approve',
             {'shop_id': self.shop.id,
              'month': self.dt.month,
              'year': self.dt.year}
        )
        self.assertEqual(response.status_code, 200)
        id = response.json()['data'].pop('id')
        dt_approved=self.dt.strftime('%d.%m.%Y')

        dttm_added = response.json()['data'].pop('dttm_added')
        data = {'code': 200,
            'data': {
              'shop_id': self.shop.id,
              'created_by': self.user1.id,
              'dt_approved': dt_approved,
            }
            , 'info': None
        }

        self.assertEqual(response.json(), data)

        response = self.api_post(
            '/api/timetable/worker_day_approve/create_worker_day_approve',
             {'shop_id': self.shop.id,
              'month': self.dt2.month,
              'year': self.dt2.year}
        )

        self.assertEqual(response.json()['code'], 200)


        response = self.api_get('/api/timetable/worker_day_approve/get_worker_day_approves?dt_approved={}&shop_id={}'.format(
            dt_approved,
            self.shop.id
        ))

        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(len(response.json()['data']), 1)

        response = self.api_get('/api/timetable/worker_day_approve/get_worker_day_approves?dt_from={}&dt_to={}&shop_id={}'.format(
            self.dt2.strftime('%d.%m.%Y'),
            (self.dt + relativedelta(months=1)).strftime('%d.%m.%Y'),
            self.shop.id
        ))

        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(len(response.json()['data']), 2)

        response = self.api_post('/api/timetable/worker_day_approve/delete_worker_day_approve',
                                 {'id': id}
        )

        self.assertEqual(response.json()['code'], 200)

        wd = WorkerDayApprove.objects.get(id=id)
        self.assertTrue(wd.dttm_deleted is not None)
