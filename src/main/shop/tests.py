from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from src.base.models import Shop
from src.timetable.models import Timetable
from src.util.test import LocalTestCase

class TestShop(LocalTestCase):

    def setUp(self):
        super().setUp()

        # print(self.shop.__dict__)
        self.timetable1_1 = Timetable.objects.create(
            shop = self.shop,
            dt = datetime.now().date().replace(day=1),
            status = 1,
            dttm_status_change = datetime.now(),
            fot=10,
            idle=10,
            lack=10,
            workers_amount=10,
            revenue=10,
            fot_revenue=10,
        )
        self.timetable1_2 = Timetable.objects.create(
            shop = self.shop,
            dt = datetime.now().date().replace(day=1) - relativedelta(months=1),
            status = 1,
            dttm_status_change = datetime.now()- relativedelta(months=1),
            fot=5,
            idle=5,
            lack=5,
            workers_amount=5,
            revenue=5,
            fot_revenue=5,
        )

        self.timetable2_1 = Timetable.objects.create(
            shop = self.shop2,
            dt = datetime.now().date().replace(day=1),
            status = 1,
            dttm_status_change = datetime.now(),
            fot=10,
            idle=10,
            lack=10,
            workers_amount=10,
            revenue=10,
            fot_revenue=10,
        )
        self.timetable2_2 = Timetable.objects.create(
            shop = self.shop2,
            dt = datetime.now().date().replace(day=1) - relativedelta(months=1),
            status = 1,
            dttm_status_change = datetime.now()- relativedelta(months=1),
            fot=5,
            idle=5,
            lack=5,
            workers_amount=5,
            revenue=5,
            fot_revenue=5,
        )

        self.timetable3_1 = Timetable.objects.create(
            shop = self.shop3,
            dt = datetime.now().date().replace(day=1),
            status = 1,
            dttm_status_change = datetime.now(),
            fot=8,
            idle=8,
            lack=8,
            workers_amount=8,
            revenue=8,
            fot_revenue=8,
        )
        self.timetable3_2 = Timetable.objects.create(
            shop = self.shop3,
            dt = datetime.now().date().replace(day=1) - relativedelta(months=1),
            status = 1,
            dttm_status_change = datetime.now()- relativedelta(months=1),
            fot=4,
            idle=4,
            lack=4,
            workers_amount=4,
            revenue=4,
            fot_revenue=4,
        )

    def test_get_department(self):
        self.auth()
        response = self.api_get('/api/shop/get_department?shop_id={}'.format(
                self.shop.id
            ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        answer = {'code': 200,
                  'data': {
                      'shops': [{
                          'id': self.shop.id,
                          'parent': self.reg_shop1.id,
                          'name': 'Shop1', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00',
                          'code': '', 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None,
                          'timezone': 'Europe/Moscow',
                          'fot': {'prev': 5, 'curr': 10, 'change': 100},
                          'lack': {'prev': 5.0, 'curr': 10.0, 'change': 100},
                          'idle': {'prev': 5.0, 'curr': 10.0, 'change': 100},
                          'workers_amount': {'prev': 5, 'curr': 10, 'change': 100},
                          'fot_revenue': {'prev': 5.0, 'curr': 10.0, 'change': 100}}],
                      'super_shop': {
                          'id': self.shop.id,
                          'parent': self.reg_shop1.id,
                          'name': 'Shop1', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00',
                          'code': '', 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None,
                          'timezone': 'Europe/Moscow',}},
                  'info': None
                  }

        self.assertEqual(response.json(), answer)

    def test_get_department_stats(self):
        self.auth()
        response = self.api_get('/api/shop/get_department_stats?shop_id={}'.format(
                self.shop.id
            ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        answer = {'code': 200,
                  'data': {
                      'shop_tts': '0/1',
                      'fot_revenue': [
                          {'dt': '01.03.2019', 'value': 0.0},
                          {'dt': '01.04.2019', 'value': 0.0},
                          {'dt': '01.05.2019', 'value': 0.0},
                          {'dt': '01.06.2019', 'value': 0.0},
                          {'dt': '01.07.2019', 'value': 0.0},
                          {'dt': '01.08.2019', 'value': 5.0},
                          {'dt': '01.09.2019', 'value': 10.0}
                      ],
                      'stats': {
                          'curr': {
                              'revenue': 10, 'lack': 10.0, 'idle': 10.0,
                              'workers_amount': 10, 'fot_revenue': 10.0},
                          'next': {}
                      }},
                  'info': None
                  }
        self.assertEqual(response.json()['data']['stats'], answer['data']['stats'])
        self.assertEqual(response.json()['data']['fot_revenue'][-1]['value'], 10)

    def test_get_department_list(self):
        self.auth()
        response = self.api_get(
            '/api/shop/get_department_list?shop_id={}&pointer=0&items_per_page=10&name=&super_shop_type=&region=&closed_before_dt=&opened_after_dt=&fot_revenue=-&revenue=-&lack=-&fot=-&idle=-&workers_amount=-&sort_type=&format=raw&sort_type=fot'.format(
                self.root_shop.id
            ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        data = {
            'pages': 1,
            'shops': [
                {'id': self.reg_shop2.id,
                 'parent': self.root_shop.id,
                 'timezone': 'Europe/Moscow',
                 'name': 'Region Shop2', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00', 'code': '', 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None,
                 'revenue': {'prev': 4, 'curr': 8, 'change': 100},
                 'lack': {'prev': 4.0, 'curr': 8.0, 'change': -100},
                 'fot': {'prev': 4.0, 'curr': 8.0, 'change': -100},
                 'idle': {'prev': 4.0, 'curr': 8.0, 'change': -100},
                 'workers_amount': {'prev': 4, 'curr': 8, 'change': 100},
                 'fot_revenue': {'prev': 4.0, 'curr': 8.0, 'change': -100}},
                {'id': self.reg_shop1.id,
                 'parent': self.root_shop.id,
                 'timezone': 'Europe/Moscow',
                 'name': 'Region Shop1', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00', 'code': '', 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None,
                 'revenue': {'prev': 10, 'curr': 20, 'change': 100},
                 'lack': {'prev': 5.0, 'curr': 10.0, 'change': -100},
                 'fot': {'prev': 10.0, 'curr': 20.0, 'change': -100},
                 'idle': {'prev': 5.0, 'curr': 10.0, 'change': -100},
                 'workers_amount': {'prev': 10, 'curr': 20, 'change': 100},
                 'fot_revenue': {'prev': 5.0, 'curr': 10.0, 'change': -100}}]
        }
        self.assertEqual(response.json()['data'], data)

    def test_get_parameters(self):
        self.auth()
        response = self.api_get(f'/api/shop/get_parameters?shop_id={self.shop.id}')
        correct_data ={
            'code': 200, 
            'data': {
                'queue_length': 3.0, 
                'idle': 0, 
                'fot': 0, 
                'less_norm': 0, 
                'more_norm': 0, 
                'tm_shop_opens': '07:00:00', 
                'tm_shop_closes': '00:00:00', 
                'shift_start': 6, 
                'shift_end': 12, 
                'restricted_start_times': '[]', 
                'restricted_end_times': '[]', 
                'min_change_time': 12, 
                'absenteeism': 0, 
                'even_shift': False, 
                'paired_weekday': False, 
                'exit1day': False, 
                'exit42hours': False, 
                'process_type': 'N'
            }, 
            'info': None
        }
        res = response.json()
        self.assertEqual(res, correct_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(res['code'], 200)

    def test_set_parameters(self):
        self.auth()
        data = {
            'shop_id': self.shop.id,
            'queue_length': 4.0, 
            'idle': 2, 
            'fot': 1, 
            'less_norm': 4, 
            'more_norm': 6, 
            'tm_shop_opens': '04:00:00', 
            'tm_shop_closes': '00:00:00', 
            'shift_start': 5, 
            'shift_end': 14, 
            'restricted_start_times': '[]', 
            'restricted_end_times': '[]', 
            'min_change_time': 10, 
            'absenteeism': 1, 
            'even_shift_morning_evening': True, 
            'paired_weekday': True, 
            'exit1day': True, 
            'exit42hours': True, 
            'process_type': 'P'
        }
        response = self.api_post(
            '/api/shop/set_parameters',
            data
        )
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(response.status_code, 200)
        data.pop('shop_id')
        data['tm_shop_opens'] = time(4, 0)
        data['tm_shop_closes'] = time(0, 0)
        shop_dict = Shop.objects.filter(id=self.shop.id).values(
            'queue_length', 
            'idle', 
            'fot', 
            'less_norm', 
            'more_norm', 
            'tm_shop_opens', 
            'tm_shop_closes', 
            'shift_start', 
            'shift_end', 
            'restricted_start_times', 
            'restricted_end_times', 
            'min_change_time', 
            'absenteeism', 
            'even_shift_morning_evening', 
            'paired_weekday', 
            'exit1day', 
            'exit42hours', 
            'process_type',
        )[0]
        self.assertEqual(shop_dict, data)
