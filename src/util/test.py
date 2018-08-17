import json
from django.test import TestCase

from src.db.models import (
    User,
    WorkerDay,
    CameraCashboxStat,
    CashboxType,
    PeriodDemand,
    Shop,
    SuperShop,
    Cashbox,
    CameraCashbox,
    WorkerDayCashboxDetails,
    Slot,
    UserWeekdaySlot,
    WorkerCashboxInfo
)

import datetime
from django.utils.timezone import now


class LocalTestCase(TestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        dttm_now = now() + datetime.timedelta(hours=3)

        self.superShop = SuperShop.objects.create(title='SuperShop1')

        self.shop = Shop.objects.create(
            id=1,
            super_shop=self.superShop,
            title='Shop1',
            hidden_title='Shop1',
            break_triplets=[[0, 360, [30]], [360, 540, [30, 30]], [540, 780, [30, 30, 15]]]
        )
        self.shop2 = Shop.objects.create(
            id=2,
            super_shop=self.superShop,
            title='Shop2',
            hidden_title='Shop2',
        )
        self.user1 = User.objects.create_user(self.USER_USERNAME, self.USER_EMAIL, self.USER_PASSWORD, id=1,
                                              shop=self.shop)
        # self.user1 = create_user(user_id=1, shop_id=self.shop, username='user1')
        self.user2 = create_user(user_id=2, shop_id=self.shop, username='user2')
        self.user3 = create_user(user_id=3, shop_id=self.shop, username='user3')
        self.user4 = create_user(user_id=4, shop_id=self.shop, username='user4',
                                 dt_fired=(dttm_now - datetime.timedelta(days=1)).date())
        self.cashboxType1 = create_cashbox_type(self.shop, 'тип_кассы_1', id=1,
                                                dttm_last_update_queue=datetime.datetime(2018, 6, 18, 8, 30, 0))

        self.cashboxType2 = create_cashbox_type(self.shop, 'тип_кассы_2', id=2,
                                                dttm_last_update_queue=datetime.datetime(2018, 6, 18, 9, 0, 0))

        self.cashboxType3 = create_cashbox_type(self.shop, 'тип_кассы_3', id=3,
                                                dttm_last_update_queue=datetime.datetime(2018, 6, 18, 8, 30, 0),
                                                dttm_deleted=dttm_now - datetime.timedelta(days=1))

        self.cashboxType4 = create_cashbox_type(self.shop, 'тип_кассы_4', id=4)

        self.cashbox1 = Cashbox.objects.create(
            type=self.cashboxType1,
            number=1,
            id=1,
        )

        self.cashbox2 = Cashbox.objects.create(
            type=self.cashboxType2,
            number=2,
            id=2,
        )

        self.cashbox3 = Cashbox.objects.create(
            type=self.cashboxType1,
            dttm_deleted=dttm_now - datetime.timedelta(days=3),
            number=3,
            id=3,
        )

        for i in range(5, 10):
            Cashbox.objects.create(
                type=self.cashboxType3,
                number=i,
                id=i,
            )

        # create_period_demand(dttm_now, 10, 50, 1, 4, 3, self.cashboxType)
        # create_period_demand(datetime.datetime(2018, 5, 10, 0, 0), 10, 50, 1, 4, 3, self.cashboxType)
        # create_period_demand(datetime.datetime(2018, 6, 18, 7, 30), 100, 50, 1, 4, 3, self.cashboxType)
        # create_period_demand(datetime.datetime(2018, 6, 18, 7, 30), 101, 23, 1, 4, 3, self.cashboxType)
        # create_period_demand(datetime.datetime(2018, 6, 18, 7, 30), 10, 50, 1, 4, 3, self.cashboxType2)
        # create_period_demand(datetime.datetime(2018, 5, 6, 0, 0), 10, 50, 1, 4, 3, self.cashboxType)

        for i in range(1, 21):
            create_period_demand(datetime.datetime(2018, 7, i, 0, 0), 10, 50, 1, 4, 3, self.cashboxType1)
            create_period_demand(datetime.datetime(2018, 6, i, 7, 30), i * 2, i, 1, 4, 3, self.cashboxType1)
            create_period_demand(datetime.datetime(2018, 6, 18, 7, 30), i, i * 3, 1, i * 4, i, self.cashboxType2)

            self.worker_day1 = create_work_day(self.shop.id, self.user1, dt=datetime.datetime(2018, 6, i))
            self.worker_day2 = create_work_day(self.shop.id, self.user2, dt=datetime.datetime(2018, 6, i))
            self.worker_day3 = create_work_day(self.shop.id, self.user3, dt=datetime.datetime(2018, 6, i))
            self.worker_day4 = create_work_day(self.shop.id, self.user1, dt=datetime.datetime(2018, 7, i))

            if i < 10:
                self.worker_day3 = create_work_day(self.shop.id, self.user3, dt=datetime.datetime(2018, 7, i), type=5)
            else:
                self.worker_day3 = create_work_day(self.shop.id, self.user3, dt=datetime.datetime(2018, 7, i))

            WorkerDayCashboxDetails.objects.create(
                status=WorkerDayCashboxDetails.TYPE_WORK,
                worker_day=self.worker_day1,
                on_cashbox=self.cashbox1,
                cashbox_type=self.cashboxType1,
                is_tablet=True,
                tm_from=datetime.time(9, 0, 0),
                tm_to=datetime.time(18, 0, 0),
            )

            WorkerDayCashboxDetails.objects.create(
                status=WorkerDayCashboxDetails.TYPE_WORK,
                worker_day=self.worker_day2,
                on_cashbox=self.cashbox1,
                cashbox_type=self.cashboxType1,
                is_tablet=True,
                tm_from=(dttm_now - datetime.timedelta(hours=3)).time(),
                tm_to=(dttm_now + datetime.timedelta(hours=3)).time()
            )

        self.worker_day = create_work_day(self.shop.id, self.user1, dt=dttm_now.date())
        self.worker_day2 = create_work_day(self.shop.id, self.user2, dt=dttm_now.date())
        self.worker_day3 = create_work_day(self.shop.id, self.user3, dt=dttm_now.date())

        WorkerDayCashboxDetails.objects.create(worker_day=self.worker_day, on_cashbox=self.cashbox1, is_tablet=True,
                                               cashbox_type=self.cashboxType1, tm_to=None,
                                               tm_from=(dttm_now - datetime.timedelta(hours=3)).time(),
                                               )

        self.cameracashbox = CameraCashbox.objects.create(name='Camera_1', cashbox=self.cashbox1)
        test_time = dttm_now
        for i in range(1, 20):
            create_camera_cashbox_stat(self.cameracashbox, test_time, i)
            test_time -= datetime.timedelta(seconds=10)

        self.slot1 = Slot.objects.create(
            name='Slot1',
            shop=self.shop,
            tm_start=datetime.time(hour=7),
            tm_end=datetime.time(hour=12),
            id=1,
        )
        Slot.objects.create(
            name='Slot2',
            shop=self.shop,
            tm_start=datetime.time(hour=12),
            tm_end=datetime.time(hour=17),
            id=2,
        )

        UserWeekdaySlot.objects.create(
            weekday=0,
            slot=self.slot1,
            worker=self.user1,
            id=1
        )

        WorkerCashboxInfo.objects.create(
            id=1,
            worker=self.user1,
            cashbox_type=self.cashboxType1,
        )
        WorkerCashboxInfo.objects.create(
            id=2,
            worker=self.user1,
            cashbox_type=self.cashboxType2,
        )
        WorkerCashboxInfo.objects.create(
            id=3,
            worker=self.user2,
            cashbox_type=self.cashboxType1,
        )
        WorkerCashboxInfo.objects.create(
            id=4,
            worker=self.user2,
            cashbox_type=self.cashboxType2,
        )

    def auth(self):
        self.client.post(
            '/api/auth/signin',
            {
                'username': self.USER_USERNAME,
                'password': self.USER_PASSWORD
            }
        )

    def api_get(self, *args, **kwargs):
        response = self.client.get(*args, **kwargs)
        response.json = json.loads(response.content.decode('utf-8'))
        return response

    def api_post(self, *args, **kwargs):
        response = self.client.post(*args, **kwargs)
        response.json = json.loads(response.content.decode('utf-8'))
        return response


def create_user(user_id, shop_id, username, dt_hired=None,
                dt_fired=None):
    user = User.objects.create(
        id=user_id,
        username=username,
        shop=shop_id,
        dt_hired=dt_hired,
        dt_fired=dt_fired
    )
    return user


def create_work_day(worker_shop_id, worker, dt, type=2, tm_work_start=datetime.time(hour=12, minute=0, second=0),
                    tm_work_end=datetime.time(hour=23, minute=0, second=0)):
    worker_day = WorkerDay.objects.create(
        worker_shop_id=worker_shop_id,
        worker=worker,
        type=type,
        dt=dt,
        tm_work_start=tm_work_start,
        tm_work_end=tm_work_end,
    )
    return worker_day


def create_camera_cashbox_stat(camera_cashbox_obj, dttm, queue):
    CameraCashboxStat.objects.create(
        camera_cashbox=camera_cashbox_obj,
        dttm=dttm,
        queue=queue,
    )


def create_cashbox_type(shop, name, dttm_last_update_queue=None, dttm_deleted=None, id=None):
    cashbox_type = CashboxType.objects.create(
        id=id,
        shop=shop,
        name=name,
        dttm_deleted=dttm_deleted,
        dttm_last_update_queue=dttm_last_update_queue
    )
    return cashbox_type


def create_period_demand(dttm_forecast, clients, products, type, queue_wait_time,
                         queue_wait_length,
                         cashbox_type):
    PeriodDemand.objects.create(
        dttm_forecast=dttm_forecast,
        clients=clients,
        products=products,
        type=type,
        queue_wait_time=queue_wait_time,
        queue_wait_length=queue_wait_length,
        cashbox_type=cashbox_type
    )
