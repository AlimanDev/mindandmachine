from src.util.test import LocalTestCase


class TestDemand(LocalTestCase):
    def setUp(self):
        super().setUp()

    def test_get_indicators(self):

        # response = self.api_get('/api/demand/get_indicators?from_dt=08.5.2018&to_dt=08.7.2018&type=L')
        # self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AuthRequired')
        self.auth()

        response = self.api_get('/api/demand/get_indicators?from_dt=06.6.2018&to_dt=07.6.2018&type=L')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['mean_bills'],  8.666666666666666)
        self.assertEqual(response.json['data']['mean_codes'], 4.333333333333333)
        self.assertEqual(response.json['data']['mean_bill_codes'], 0.5)
        self.assertEqual(response.json['data']['mean_hour_bills'], 0.7647058823529411)
        self.assertEqual(response.json['data']['mean_hour_codes'], 0.38235294117647056)
        # self.assertEqual(response.json['data']['growth'], 0)
        self.assertEqual(response.json['data']['total_bills'], 26.0)
        self.assertEqual(response.json['data']['total_codes'], 13.0)
