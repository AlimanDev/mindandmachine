import datetime
from src.util.test import LocalTestCase
from src.db.models import WorkerDayCashboxDetails
from src.util.models_converter import BaseConverter
from django.utils.timezone import now


class TestTablet(LocalTestCase):

    def setUp(self):
        super().setUp()

    def test_get_cashboxes_info(self):
        self.auth()
        response = self.api_get('/api/tablet/get_cashboxes_info?shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        print(response.json)

        self.assertEqual(response.json['data']['1']['with_queue'], True)
        self.assertEqual(response.json['data']['1']['cashbox'][0]['number'], 1)
        self.assertEqual(response.json['data']['1']['cashbox'][0]['status'], 'O')
        self.assertEqual(response.json['data']['1']['cashbox'][0]['queue'], 5.5)
        self.assertEqual(response.json['data']['1']['cashbox'][0]['user_id'], '1')

    def test_get_cashiers_info(self):
        self.auth()
        response = self.api_get('/api/tablet/get_cashiers_info?shop_id=1&dttm={}'
                                .format(BaseConverter.convert_datetime(now() + datetime.timedelta(hours=3))))
        print(response.json)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['1']['worker_id'], 1)
        self.assertEqual(response.json['data']['1']['status'], 'W')

    def test_change_cashier_status(self):
        def api_cashiers_inf(worker_id, status, shop_id=1):
            response = self.api_get('/api/tablet/get_cashiers_info?shop_id={}&dttm={}'
                                    .format(shop_id,
                                            BaseConverter.convert_datetime(now() + datetime.timedelta(hours=3))))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['code'], 200)
            self.assertEqual(response.json['data']['{}'.format(worker_id)]['worker_id'], worker_id)
            self.assertEqual(response.json['data']['{}'.format(worker_id)]['status'], status)

        def api_change_cashier_status(worker_id, status, cashbox_id=None):
            response = self.api_post('/api/tablet/change_cashier_status', {
                'worker_id': worker_id,
                'status': status,
                'cashbox_id': self.cashbox2.id,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['code'], 200)
            self.assertEqual(response.json['data'], {'{}'.format(worker_id): {'worker_id': worker_id, 'status': status,
                                                                              'cashbox_id': cashbox_id}})

        self.auth()

        response = self.api_post('/api/tablet/change_cashier_status', {
            'worker_id': self.user1.id,
            'status': WorkerDayCashboxDetails.TYPE_WORK,
            'cashbox_id': self.cashbox1.id,
        })
        print(response.json)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 400)
        self.assertEqual(response.json['data']['error_message'], 'cashbox already opened')

        response = self.api_get('/api/tablet/get_cashiers_info?shop_id=1&dttm={}'
                                .format(BaseConverter.convert_datetime(now() + datetime.timedelta(hours=3))))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['1']['worker_id'], 1)
        self.assertEqual(response.json['data']['1']['status'], 'W')

        response = self.api_get('/api/tablet/get_cashboxes_info?shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['1']['cashbox'][0]['status'], 'O')

        api_change_cashier_status(worker_id=self.user2.id, status=WorkerDayCashboxDetails.TYPE_WORK,
                                  cashbox_id=self.cashbox2.id)
        api_cashiers_inf(worker_id=self.cashbox2.id, status='W', shop_id=self.shop.id)

        api_change_cashier_status(worker_id=self.user2.id, status=WorkerDayCashboxDetails.TYPE_BREAK)
        api_cashiers_inf(worker_id=self.cashbox2.id, status='B', shop_id=self.shop.id)

        api_change_cashier_status(worker_id=self.user2.id, status=WorkerDayCashboxDetails.TYPE_WORK,
                                  cashbox_id=self.cashbox2.id)

        api_cashiers_inf(worker_id=self.cashbox2.id, status='W', shop_id=self.shop.id)

        api_change_cashier_status(worker_id=self.user2.id, status=WorkerDayCashboxDetails.TYPE_FINISH)
        api_cashiers_inf(worker_id=self.cashbox2.id, status='H', shop_id=self.shop.id)
