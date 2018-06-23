import datetime

from src.util.test import LocalTestCase
from src.db.models import User, Shop, SuperShop, Slot, UserWeekdaySlot, PeriodDemand, CashboxType, Cashbox, WorkerDay
import json


class TestDemand(LocalTestCase):
    USER_USERNAME = 'admin_user1'
    USER_EMAIL = 'test@mail.ru'
    USER_PASSWORD = '1111'

    def setUp(self):
        self.superShop = SuperShop.objects.create(
            title='SuperShop1',
        )
        self.shop = Shop.objects.create(
            id=1,
            super_shop=self.superShop,
            title='Shop1',
        )

        self.user2 = User.objects.create(
            username='user2',
            shop=self.shop
        )

        self.user3 = User.objects.create(
            username='user3',
            shop=self.shop
        )

        self.user4 = User.objects.create(
            username='user4',
            shop=self.shop
        )
        self.user5 = User.objects.create(
            username='user5',
            shop=self.shop
        )

        self.user = User.objects.create_user(username=self.USER_USERNAME, email=self.USER_EMAIL,
                                             password=self.USER_PASSWORD, shop_id=1)

        self.cashboxType = CashboxType.objects.create(
            # id=1,
            shop=self.shop,
            name='касса_1',
        )

        Cashbox.objects.create(
            type=self.cashboxType,
            number=1
        )

        PeriodDemand.objects.create(
            dttm_forecast=datetime.datetime(2018, 5, 6, 0, 0),
            clients=10,
            products=50,
            type=1,
            queue_wait_time=4,
            queue_wait_length=3,
            cashbox_type_id=1
        )

        PeriodDemand.objects.create(
            dttm_forecast=datetime.datetime(2018, 5, 10, 0, 0),
            clients=10,
            products=50,
            type=1,
            queue_wait_time=4,
            queue_wait_length=3,
            cashbox_type_id=1
        )

        PeriodDemand.objects.create(
            dttm_forecast=datetime.datetime(2018, 6, 1, 0, 30),
            clients=100,
            products=111,
            type=1,
            queue_wait_time=4,
            queue_wait_length=3,
            cashbox_type_id=1
        )

        PeriodDemand.objects.create(
            dttm_forecast=datetime.datetime(2018, 6, 2, 7, 30),
            clients=50,
            products=45,
            type=1,
            queue_wait_time=4,
            queue_wait_length=3,
            cashbox_type_id=1
        )

        WorkerDay.objects.create(
            worker_shop_id=self.shop.id,
            worker=self.user,
            type=2,
            dt=datetime.datetime(2018, 6, 9),
            tm_work_start=datetime.time(hour=12, minute=0, second=0),
            tm_work_end=datetime.time(hour=23, minute=0, second=0)
        )

        WorkerDay.objects.create(
            worker_shop_id=self.shop.id,
            worker=self.user,
            type=2,
            dt=datetime.datetime(2018, 7, 7),
            tm_work_start=datetime.time(hour=12, minute=0, second=0),
            tm_work_end=datetime.time(hour=23, minute=0, second=0)
        )

        WorkerDay.objects.create(
            worker_shop_id=self.shop.id,
            worker=self.user,
            type=2,
            dt=datetime.datetime(2018, 6, 10),
            tm_work_start=datetime.time(hour=12, minute=0, second=0),
            tm_work_end=datetime.time(hour=23, minute=0, second=0)
        )
        WorkerDay.objects.create(
            worker_shop_id=self.shop.id,
            worker=self.user2,
            type=2,
            dt=datetime.datetime(2018, 6, 10),
            tm_work_start=datetime.time(hour=12, minute=0, second=0),
            tm_work_end=datetime.time(hour=23, minute=0, second=0)
        )

        WorkerDay.objects.create(
            worker_shop_id=self.shop.id,
            worker=self.user3,
            type=2,
            dt=datetime.datetime(2018, 5, 6),
            tm_work_start=datetime.time(hour=12, minute=0, second=0),
            tm_work_end=datetime.time(hour=23, minute=0, second=0)
        )

        WorkerDay.objects.create(
            worker_shop_id=self.shop.id,
            worker=self.user3,
            type=2,
            dt=datetime.datetime(2018, 7, 9),
            tm_work_start=datetime.time(hour=12, minute=0, second=0),
            tm_work_end=datetime.time(hour=23, minute=0, second=0)
        )

    def auth(self):
        self.client.post(
            '/api/auth/signin',
            {
                'username': self.USER_USERNAME,
                'password': self.USER_PASSWORD
            }
        )

    def test_get_indicators(self):

        response = self.api_get('/api/demand/get_indicators?from_dt=08.5.2018&to_dt=08.7.2018&type=L')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 403)
        self.assertEqual(response.json['data']['error_type'], 'AuthRequired')

        self.auth()

        response = self.api_get('/api/demand/get_indicators?from_dt=08.5.2018&to_dt=08.7.2018&type=L')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['mean_bills'], 80)
        self.assertEqual(response.json['data']['mean_codes'], 103)
        self.assertEqual(response.json['data']['mean_bill_codes'], 1.2875)
        self.assertEqual(response.json['data']['mean_hour_bills'], 0.15180265654648956)
        self.assertEqual(response.json['data']['mean_hour_codes'], 0.1954459203036053)
        # self.assertEqual(response.json['data']['growth'], 0)
        self.assertEqual(response.json['data']['total_bills'], 160)
        self.assertEqual(response.json['data']['total_codes'], 206)
