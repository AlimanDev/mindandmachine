import datetime

from src.util.test import LocalTestCase
from src.db.models import User, Shop, SuperShop, PeriodDemand, CashboxType, Cashbox, WorkerDay, CameraCashbox, \
    CameraCashboxStat
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
            shop=self.shop,
            name='тип_кассы_1',
            dttm_last_update_queue=datetime.datetime(2018, 6, 2, 7, 30, 0)
        )

        self.cashboxType2 = CashboxType.objects.create(
            shop=self.shop,
            name='тип_кассы_2',
            # dttm_last_update_queue=datetime.datetime(2018, 5, 6, 12, 12, 12)
        )

        self.cashbox = Cashbox.objects.create(
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

        self.cameracashbox = CameraCashbox.objects.create(
            name='Camera_1',
            cashbox=self.cashbox
        )
        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 30, 3),
            queue=5
        )

        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 30, 1),
            queue=5
        )

        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 30, 2),
            queue=5
        )
        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 30, 3),
            queue=5
        )

        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 30, 3),
            queue=5
        )
        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 30, 5),
            queue=5000000
        )
        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 31, 5),
            queue=5000000
        )
        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 31, 3),
            queue=5
        )

        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 31, 1),
            queue=5
        )

        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 31, 2),
            queue=5
        )
        CameraCashboxStat.objects.create(
            camera_cashbox=self.cameracashbox,
            dttm=datetime.datetime(2018, 6, 2, 7, 31, 3),
            queue=5
        )

        # CameraCashboxStat.objects.create(
        #     camera_cashbox=self.cameracashbox,
        #     dttm=datetime.datetime(2018, 6, 2, 7, 31, 5),
        #     queue=5000000
        # )

    def auth(self):
        self.client.post(
            '/api/auth/signin',
            {
                'username': self.USER_USERNAME,
                'password': self.USER_PASSWORD
            }
        )

    def test_my_func(self):
        self.auth()

        def __div_safe(__a, __b):
            return __a / __b if __b > 0 else None

        from datetime import datetime, timedelta, time
        def update_queue():
            count = 0
            queue_in_minute = 0

            last_update_queue = CashboxType.objects.all().filter(dttm_last_update_queue__isnull=False)\
                .values('id', 'dttm_last_update_queue')
            print(last_update_queue[0]['dttm_last_update_queue'])

            for items in last_update_queue:
                queues = CameraCashboxStat.objects.all().filter(
                    camera_cashbox__cashbox__type__id=items['id'],
                    dttm__gte=items['dttm_last_update_queue'],
                    dttm__lt=items['dttm_last_update_queue'] + timedelta(seconds=1800)
                  ).values('queue').annotate()
                print(queues)

            # cam_stats_obj = CameraCashboxStat.objects.all().filter(dttm_forecast__gte=dttm_from,
            #                                                        dttm_forecast__lte=dttm_to,
            #                                                        camera_cashbox__in=(1)).order_by('dttm')

            # 'dttm_last_update_queue', 'queue'

            # cam_stats_obj = CameraCashboxStat.objects.all().filter(camera_cashbox__in=(1)).order_by('dttm')
            # minute = cam_stats_obj[0].dttm.minute
            # print('\nstart - {}'.format(minute))
            # for obj in cam_stats_obj:
            #     if obj.dttm.minute == minute:
            #         queue_in_minute += obj.queue
            #         count += 1
            #     else:
            #         minute = obj.dttm.minute
            #         mean_queue = __div_safe(queue_in_minute, count)
            #         print('mean-{}'.format(mean_queue))
            #         queue_in_minute = obj.queue
            #         count = 1
            #
            # mean_queue = __div_safe(queue_in_minute, count)
            # print('mean-{}'.format(mean_queue))

        update_queue()


