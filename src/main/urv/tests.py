from src.util.test import LocalTestCase


class TestURV(LocalTestCase):
    def setUp(self):
        super().setUp()

    def test_get_indicators(self):
        self.auth()
        response = self.api_get('/api/urv/get_indicators?from_dt=09.09.2019&to_dt=16.09.2019&shop_id={}'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

    def test_get_user_urv(self):
        self.auth()
        response = self.api_get('/api/urv/get_user_urv?worker_ids=[]&from_dt=01.10.2019&to_dt=08.10.2019&amount_per_page=64&show_outstaff=false&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
