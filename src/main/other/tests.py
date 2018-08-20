from src.util.test import LocalTestCase
import json


class TestCashboxTypes(LocalTestCase):
    def setUp(self):
        super().setUp()

    def test_get_slots(self):
        # response = self.api_get('/api/other/get_slots?user_id=1')
        # self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_get('/api/other/get_slots?user_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['slots'],
                         {
                             '0': [
                                 {
                                     'id': 1,
                                     'name': 'Slot1',
                                     'tm_start': '07:00:00',
                                     'tm_end': '12:00:00',
                                 },
                             ],
                         },
                         )

        response = self.api_get('/api/other/get_slots?user_id=3')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['slots'], {})

    def test_get_all_slots(self):
        # response = self.api_get('/api/other/get_all_slots?shop_id=1')
        # self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_get('/api/other/get_all_slots?shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['slots'], [
            {
                'id': 1,
                'name': 'Slot1',
                'tm_start': '07:00:00',
                'tm_end': '12:00:00',
            },
            {
                'id': 2,
                'name': 'Slot2',
                'tm_start': '12:00:00',
                'tm_end': '17:00:00',
            },
        ])

        response = self.api_get('/api/other/get_all_slots?shop_id=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['slots'], [])

    def test_set_slots(self):
        # response = self.api_post('/api/other/set_slot')
        # self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_post('/api/other/set_slot', {
            # 'weekday': 0,
            'slots': json.dumps({0: [self.slot1.id]}),
            'user_id': self.user1.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

    def test_set_slots2(self):
        # response = self.api_post('/api/other/set_slot')
        # self.assertEqual(response.status_code, 200)
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_post('/api/other/set_slot', {
            # 'weekday': 0,
            'slots': json.dumps({0: [self.slot1.id], 1: [self.slot1.id], 2: []}),
            'user_id': self.user1.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        response = self.api_post('/api/other/set_slot', {
            # 'weekday': 0,
            'slots': json.dumps({0: [self.slot1.id], 1: [], 2: []}),
            'user_id': self.user1.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        response = self.api_post('/api/other/set_slot', {
            # 'weekday': 0,
            'slots': json.dumps({0: [self.slot1.id], 1: [500], 2: []}),
            'user_id': self.user1.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 400)
