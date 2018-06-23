import datetime

from src.util.test import LocalTestCase
from src.db.models import User, Shop, SuperShop, Slot, WorkerConstraint, UserWeekdaySlot
import json


class TestCashboxTypes(LocalTestCase):
    def setUp(self):
        super().setUp()

        self.superShop = SuperShop.objects.create(
          title='SuperShop1',
        )
        self.shop = Shop.objects.create(
          id=1,
          super_shop=self.superShop,
          title='Shop1',
        )
        self.user = User.objects.create(
          id=1,
          shop=self.shop,
        )
        self.slot1 = Slot.objects.create(
          name='Slot1',
          shop=self.shop,
          tm_start=datetime.time(hour=7),
          tm_end=datetime.time(hour=12),
        )
        Slot.objects.create(
          name='Slot2',
          shop=self.shop,
          tm_start=datetime.time(hour=12),
          tm_end=datetime.time(hour=17),
        )

        UserWeekdaySlot.objects.create(
          weekday=0,
          slot=self.slot1,
          worker=self.user,
        )

    def test_get_slots(self):
        response = self.api_get('/api/other/get_slots?user_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 403)
        self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

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
        response = self.api_get('/api/other/get_all_slots?shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 403)
        self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

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
        response = self.api_post('/api/other/set_slot')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 403)
        self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_post('/api/other/set_slot', {
          # 'weekday': 0,
          'slots': json.dumps({0: [self.slot1.id]}),
          'user_id': self.user.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

    def test_set_slots2(self):
        response = self.api_post('/api/other/set_slot')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 403)
        self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_post('/api/other/set_slot', {
          # 'weekday': 0,
          'slots': json.dumps({0: [self.slot1.id], 1:[self.slot1.id], 2:[]}),
          'user_id': self.user.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        response = self.api_post('/api/other/set_slot', {
            # 'weekday': 0,
            'slots': json.dumps({0: [self.slot1.id], 1: [], 2: []}),
            'user_id': self.user.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        response = self.api_post('/api/other/set_slot', {
            # 'weekday': 0,
            'slots': json.dumps({0: [self.slot1.id], 1: [500], 2: []}),
            'user_id': self.user.id,
        })
        # constraints = constraint.tm for constraint in WorkerConstraint.objects.filter(worker=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 400)



