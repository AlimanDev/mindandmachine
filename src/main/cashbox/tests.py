from src.util.test import LocalTestCase, WorkType, datetime


class TestCashbox(LocalTestCase):

    def setUp(self):
        super().setUp()
        WorkType.objects.update(dttm_added=datetime.datetime(2018, 1, 1, 0, 0, 0))

    def test_get_cashboxes_open_time(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_cashboxes_open_time?shop_id={}&from_dt=02.6.2018&to_dt=2.6.2018'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        # {'1': {'share_time': 0}, '2': {'share_time': 0}, '3': {'share_time': 0}
        # self.assertEqual(response.json['data'], {
        #     '1': {'share_time': 88.237},
        #     '2': {'share_time': 35.295}})
        response = self.api_get('/api/cashbox/get_cashboxes_open_time?shop_id={}&from_dt=02.6.2018&to_dt=20.8.2018'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        # {'1': {'share_time': 0}, '2': {'share_time': 0}, '3': {'share_time': 0}}
        # self.assertEqual(response.json['code'], 200)
        # self.assertEqual(response.json['data'], {
        #     '1': {'share_time': 20.956},
        #     '2': {'share_time': 8.382}})


    def test_get_types(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_types?shop_id={}'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        # Поступает больше данных, чем мы проверяем.
        # self.assertEqual(response.json['data'], [
        #     {'id': 2, 'dttm_added': '00:00:00 01.01.2018', 'dttm_deleted': None, 'shop': 1, 'name': 'тип_кассы_2',
        #      ''
        #      'speed_coef': 1.0},
        #     {'id': 1, 'dttm_added': '00:00:00 01.01.2018', 'dttm_deleted': None, 'shop': 1, 'name': 'тип_кассы_1',
        #      'speed_coef': 1.0}
        # ])

    def test_get_cashboxes(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_cashboxes?shop_id={}&work_type_ids=[]'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(len(response.json['data']['work_types']), 3)
        self.assertEqual(len(response.json['data']['cashboxes']), 3)

    def test_create_cashbox(self):
        self.auth()
        response = self.api_post('/api/cashbox/create_cashbox', {
            'work_type_id': 1,
            'number': 1
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 400)
        self.assertEqual(response.json['data']['error_type'], 'AlreadyExist')
