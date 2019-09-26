from datetime import datetime
from dateutil.relativedelta import relativedelta

from src.util.test import LocalTestCase
from src.db.models import Timetable


class TestShop(LocalTestCase):

    def setUp(self):
        super().setUp(periodclients=False)

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
        self.assertEqual(response.json['code'], 200)
        answer = {'code': 200,
                  'data': {
                      'shops': [{
                          'id': self.shop.id,
                          'parent': self.reg_shop1.id,
                          'title': 'Shop1', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00',
                          'code': None, 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None,
                          'fot': {'prev': 5, 'curr': 10, 'change': 100},
                          'lack': {'prev': 5.0, 'curr': 10.0, 'change': 100},
                          'idle': {'prev': 5.0, 'curr': 10.0, 'change': 100},
                          'workers_amount': {'prev': 5, 'curr': 10, 'change': 100},
                          'fot_revenue': {'prev': 5.0, 'curr': 10.0, 'change': 100}}],
                      'super_shop': {
                          'id': self.shop.id,
                          'parent': self.reg_shop1.id,
                          'title': 'Shop1', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00',
                          'code': None, 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None}},
                  'info': None
                  }

        self.assertEqual(response.json, answer)

    def test_get_department_stats(self):
        self.auth()
        response = self.api_get('/api/shop/get_department_stats?shop_id={}'.format(
                self.shop.id
            ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
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
        self.assertEqual(response.json['data']['stats'], answer['data']['stats'])
        self.assertEqual(response.json['data']['fot_revenue'][-1]['value'], 10)

    def test_get_department_list(self):
        self.auth()
        response = self.api_get(
            '/api/shop/get_department_list?shop_id={}&pointer=0&items_per_page=10&title=&super_shop_type=&region=&closed_before_dt=&opened_after_dt=&fot_revenue=-&revenue=-&lack=-&fot=-&idle=-&workers_amount=-&sort_type=&format=raw&sort_type=fot'.format(
                self.root_shop.id
            ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        data = {
            'pages': 1,
            'shops': [
                {'id': self.reg_shop2.id,
                 'parent': self.root_shop.id,
                 'title': 'Region Shop2', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00', 'code': None, 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None,
                 'revenue': {'prev': 4, 'curr': 8, 'change': 100},
                 'lack': {'prev': 4.0, 'curr': 8.0, 'change': -100},
                 'fot': {'prev': 4.0, 'curr': 8.0, 'change': -100},
                 'idle': {'prev': 4.0, 'curr': 8.0, 'change': -100},
                 'workers_amount': {'prev': 4, 'curr': 8, 'change': 100},
                 'fot_revenue': {'prev': 4.0, 'curr': 8.0, 'change': -100}},
                {'id': self.reg_shop1.id,
                 'parent': self.root_shop.id,
                 'title': 'Region Shop1', 'tm_shop_opens': '07:00:00', 'tm_shop_closes': '00:00:00', 'code': None, 'address': None, 'type': 's', 'dt_opened': None, 'dt_closed': None,
                 'revenue': {'prev': 10, 'curr': 20, 'change': 100},
                 'lack': {'prev': 5.0, 'curr': 10.0, 'change': -100},
                 'fot': {'prev': 10.0, 'curr': 20.0, 'change': -100},
                 'idle': {'prev': 5.0, 'curr': 10.0, 'change': -100},
                 'workers_amount': {'prev': 10, 'curr': 20, 'change': 100},
                 'fot_revenue': {'prev': 5.0, 'curr': 10.0, 'change': -100}}]
        }
        self.assertEqual(response.json['data'], data)
