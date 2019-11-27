import json
import datetime
from src.db.models import Employment, Timetable, WorkerDay, Slot, WorkerDayCashboxDetails, WorkerCashboxInfo
from src.util.test import LocalTestCase
from django.utils.timezone import now

from src.util.models_converter import BaseConverter


from django.conf import settings
from unittest.mock import Mock, patch


settings.CELERY_TASK_ALWAYS_EAGER = True



class TestAutoSettings(LocalTestCase):
    def test_get_status(self):
        self.auth()

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(response.json()['data']['status'], 'R')

    def test_set_selected_cashiers(self):
        self.auth()

        employment_cnt = Employment.objects.filter(
            shop=self.shop,
        ).count()

        ids=[self.user2.id, self.user3.id]
        response = self.api_post('/api/timetable/auto_settings/set_selected_cashiers',
                                 {'worker_ids': json.dumps(ids), 'shop_id': self.shop.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        employments = Employment.objects.filter(
            shop=self.shop,
            user_id__in=ids,
            auto_timetable=True
        )
        self.assertEqual(employments.count(), 2)

        employments = Employment.objects.filter(
            shop=self.shop,
            auto_timetable=False
        )
        self.assertEqual(employments.count(), employment_cnt - 2)

    # {'error_type': 'InternalError', 'error_message': 'Внутренняя ошибка сервера'} // no timetable_id
    # @skip("set timetable 500")
    def test_set_timetable(self):

        self.auth()

        timetable = Timetable.objects.create(
            shop = self.shop,
            dt = now().date().replace(day=1),
            status = Timetable.Status.PROCESSING.value,
            dttm_status_change = now()
        )
        dt = now().date()
        tm_from = datetime.time(10,0,0)
        tm_to = datetime.time(20,0,0)

        dttm_from = BaseConverter.convert_datetime(
            datetime.datetime.combine(dt, tm_from),
        )

        dttm_to = BaseConverter.convert_datetime(
            datetime.datetime.combine(dt, tm_to),
        )

        self.assertEqual(len(WorkerDay.objects.all()), 0)
        self.assertEqual(len(WorkerDayCashboxDetails.objects.all()), 0)

        response = self.api_post('/api/timetable/auto_settings/set_timetable', {
            'timetable_id': timetable.id,
            'data': json.dumps({
                'timetable_status': 'R',
                'users': {
                    self.user3.id:{
                        'workdays': [
                            {'dt': BaseConverter.convert_date(dt),
                             'type':'W',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             'details': [{
                                 'dttm_from': dttm_from,
                                 'dttm_to': dttm_to,
                                 'type': self.work_type2.id
                             }]

                             }
                        ]
                    },
                    self.user4.id: {
                        'workdays': [
                            {'dt': BaseConverter.convert_date(dt),
                             'type':'H',
                             'dttm_work_start': dttm_from,
                             'dttm_work_end': dttm_to,
                             }
                        ]
                    }
                }
            })
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        wd = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user3,
            dt=dt,
            dttm_work_start=datetime.datetime.combine(dt, tm_from),
            dttm_work_end=datetime.datetime.combine(dt, tm_to),
            type=WorkerDay.Type.TYPE_WORKDAY.value
        )
        self.assertEqual(len(wd), 1)

        self.assertEqual(WorkerDayCashboxDetails.objects.filter(
            worker_day=wd[0],
            dttm_from=datetime.datetime.combine(dt, tm_from),
            dttm_to=datetime.datetime.combine(dt, tm_to),
            work_type=self.work_type2,
        ).count(), 1)

        self.assertEqual(WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user4,
            type=WorkerDay.Type.TYPE_HOLIDAY.value,
            dt=dt
        ).count(), 1)

    @patch("src.main.timetable.auto_settings.views.requests.post")
    def test_create_timetable(self, mockpost):
        self.auth()

        mockresponse = Mock()
        mockpost.return_value = mockresponse
        mockresponse.json = lambda: {'task_id': 1}

        response = self.api_post('/api/timetable/auto_settings/create_timetable', {
            'shop_id': self.shop.id,
            'dt': BaseConverter.convert_date(now())
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
    '''
    def test_create_timetable(self):
        self.auth()
        WorkerCashboxInfo.objects.create(
            id=5,
            worker=self.user6,
            work_type=self.work_type1,
        )
        WorkerCashboxInfo.objects.create(
            id=6,
            worker=self.user7,
            work_type=self.work_type1,
        )
        Slot.objects.all().update(work_type=self.work_type1)
        response = self.api_post('/api/timetable/auto_settings/create_timetable', {
            'shop_id': self.shop.id,
            'dt': BaseConverter.convert_date(datetime.now().date()),
        })
        correct_res = {
            'code': 500, 
            'data': {
                'error_type': 'InternalError', 
                'error_message': 'Error sending data to server'
            }, 
            'info': None
        }
        self.assertEqual(response.json(), correct_res)
        correct_tt = {
            'shop_id': self.shop.id,
            'status': 3,
        }
        self.assertEqual(Timetable.objects.all().values('shop_id', 'status').last(), correct_tt)
        '''