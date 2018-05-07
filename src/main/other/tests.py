import datetime

from src.util.test import LocalTestCase
from src.db.models import User, Shop, SuperShop, Slot, WorkerConstraint

class TestCashboxTypes(LocalTestCase):
  def setUp(self):
    super().setUp()

    superShop = SuperShop.objects.create(
      title='SuperShop1',
    )
    shop = Shop.objects.create(
      id=1,
      super_shop=superShop,
      title='Shop1',
    )
    worker = User.objects.create(
      id=1,
      shop=shop,
    )

    Slot.objects.create(
      name='Slot1',
      shop=shop,
      tm_start=datetime.time(hour=7),
      tm_end=datetime.time(hour=23),
    )
    # good constraint
    WorkerConstraint.objects.create(
      tm = datetime.time(hour=4),
      worker=worker,
      weekday=0,
    )
    # bad constraint
    WorkerConstraint.objects.create(
      tm = datetime.time(hour=12),
      worker=worker,
      weekday=1,
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
    self.assertEqual(response.json['data']['schedule'], [
      {
        'name': 'Slot1',
        'tm_start': '07:00:00',
        'tm_end': '23:00:00',
      }
    ])

    # response = self.api_get('/api/other/get_schedule?shop_id=12&user_id=1')
    # self.assertEqual(response.status_code, 200)
    # self.assertEqual(response.json['code'], 200)
    # self.assertEqual(response.json['data']['schedule'], [])
