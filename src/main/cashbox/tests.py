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
        response = self.api_get('/api/cashbox/get_cashboxes_used_resource?shop_id=1&from_dt=16.06.2018&to_dt=16.06.2018')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['2']['100'], 35.29469435775095)
