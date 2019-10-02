from src.util.test import LocalTestCase


class TestWorkTypes(LocalTestCase):
    def test_get_slots(self):
        # response = self.api_get('/api/other/get_slots?user_id=1')
        # self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_get('/api/other/get_slots?user_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        response = self.api_get('/api/other/get_slots?user_id=3')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], {})

    def test_get_all_slots(self):
        # response = self.api_get('/api/other/get_all_slots?shop_id=1')
        # self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_get('/api/other/get_all_slots?shop_id={}'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], [
            {
                'id': 1,
                'name': 'Slot1',
                'tm_start': '07:00:00',
                'tm_end': '12:00:00',
                'work_type_id': None,
            },
            {
                'id': 2,
                'name': 'Slot2',
                'tm_start': '12:00:00',
                'tm_end': '17:00:00',
                'work_type_id': None,
            },
        ])

        response = self.api_get('/api/other/get_all_slots?shop_id={}'.format(
            self.shop2.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data'], [])

