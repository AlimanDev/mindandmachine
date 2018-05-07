from src.util.test import LocalTestCase
from src.db.models import User, CashboxType, Shop, SuperShop

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
    CashboxType.objects.create(
      shop=shop,
      name='CashboxType1',
    )


  def test_get_cashbox_types(self):
    response = self.api_get('/api/other/get_cashbox_types?shop_id=1')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json['code'], 403)
    self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

    self.auth()

    response = self.api_get('/api/other/get_cashbox_types?shop_id=1')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json['code'], 200)
    self.assertEqual(response.json['data']['cashbox_types'], ['CashboxType1'])

    response = self.api_get('/api/other/get_cashbox_types?shop_id=12')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json['code'], 200)
    self.assertEqual(response.json['data']['cashbox_types'], [])
