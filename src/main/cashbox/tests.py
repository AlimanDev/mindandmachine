from src.util.test import LocalTestCase, CashboxType, datetime


class TestCashbox(LocalTestCase):

    def setUp(self):
        super().setUp()
        CashboxType.objects.update(dttm_added=datetime.datetime(2018, 1, 1, 0, 0, 0))

    def test_get_cashboxes_open_time(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_cashboxes_open_time?shop_id=1&from_dt=02.6.2018&to_dt=2.6.2018')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], {
            '1': {'share_time': 88.237},
            '2': {'share_time': 35.295}})
        response = self.api_get('/api/cashbox/get_cashboxes_open_time?shop_id=1&from_dt=02.6.2018&to_dt=20.8.2018')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], {
            '1': {'share_time': 20.956},
            '2': {'share_time': 8.382}})

    def test_get_cashboxes_used_resource(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_cashboxes_used_resource?shop_id=1&from_dt=16.06.2018&to_dt=16.06.2018')
        print(response.json)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['2']['100'], 35.295)
