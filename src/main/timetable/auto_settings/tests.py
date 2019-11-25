import json
from unittest import skip

from src.db.models import User
from src.util.test import LocalTestCase, WorkerCashboxInfo, Slot, Timetable
from src.util.models_converter import BaseConverter
from datetime import datetime

class TestAutoSettings(LocalTestCase):

    def setUp(self):
        super().setUp(worker_day=True)

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

        response = self.api_post('/api/timetable/auto_settings/set_selected_cashiers',
                                 {'worker_ids': json.dumps([1, 2]), 'shop_id': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        user = User.objects.filter(id__in=[1, 2, 3]).order_by('id')
        self.assertEqual(user[0].auto_timetable, True)
        self.assertEqual(user[1].auto_timetable, True)
        self.assertEqual(user[2].auto_timetable, False)

    # {'error_type': 'InternalError', 'error_message': 'Внутренняя ошибка сервера'} // no timetable_id
    @skip("set timetable 500")
    def test_set_timetable(self):
        self.auth()

        response = self.api_post('/api/timetable/auto_settings/set_timetable', {'data': json.dumps({})})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

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