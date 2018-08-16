from src.util.test import LocalTestCase


class TestCashbox(LocalTestCase):

    def setUp(self):
        super().setUp()

    def test_get_cashboxes_open_time(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_cashboxes_open_time?shop_id=1&from_dt=02.6.2018&to_dt=2.6.2018')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], {
            '1': {'share_time': 88.237},
            '2': {'share_time': 35.295},
            '3': {'share_time': 0},
            '5': {'share_time': 0},
            '6': {'share_time': 0},
            '7': {'share_time': 0},
            '8': {'share_time': 0},
            '9': {'share_time': 0}})
        response = self.api_get('/api/cashbox/get_cashboxes_open_time?shop_id=1&from_dt=02.6.2018&to_dt=20.8.2018')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], {
            '1': {'share_time': 20.956},
            '2': {'share_time': 8.382},
            '3': {'share_time': 0},
            '5': {'share_time': 0},
            '6': {'share_time': 0},
            '7': {'share_time': 0},
            '8': {'share_time': 0},
            '9': {'share_time': 0}})

    def test_get_cashboxes_used_resource(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_cashboxes_used_resource?shop_id=1&from_dt=16.01.2018&to_dt=16.8.2018')
        print(response.json['data'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], {
            '3': {'20': 0, '40': 0, '60': 0, '80': 0, '100': 0},
            '2': {'20': 0.0, '40': 0.0, '60': 0.0, '80': 0.0, '100': 3.3140558082395253},
            '1': {'20': 0.0, '40': 0.0, '60': 2.5315704090718594, '80': 0.0, '100': 2.8997988322095845}}
                         )
