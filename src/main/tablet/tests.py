import datetime

from src.util.test import LocalTestCase, create_user, create_work_day, create_camera_cashbox_stat, create_cashbox_type, \
    create_period_demand
from src.db.models import Shop, SuperShop, Cashbox, CameraCashbox, WorkerDayCashboxDetails
from src.util.models_converter import BaseConverter
from django.utils.timezone import now


class TestTablet(LocalTestCase):

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
        self.user1 = create_user(user_id=1, shop_id=self.shop, username='user1')
        self.user2 = create_user(user_id=2, shop_id=self.shop, username='user2')
        self.user3 = create_user(user_id=3, shop_id=self.shop, username='user3')
        self.user4 = create_user(user_id=4, shop_id=self.shop, username='user4',
                                 dt_fired=(dttm_now - datetime.timedelta(days=1)).date())
        self.cashboxType = create_cashbox_type(self.shop, 'тип_кассы_1', id=1,
                                               dttm_last_update_queue=datetime.datetime(2018, 6, 18, 8, 30, 0))

        self.cashboxType2 = create_cashbox_type(self.shop, 'тип_кассы_2', id=2,
                                                dttm_last_update_queue=datetime.datetime(2018, 6, 18, 9, 0, 0))

        self.cashboxType3 = create_cashbox_type(self.shop, 'тип_кассы_3', id=3,
                                                dttm_last_update_queue=datetime.datetime(2018, 6, 18, 8, 30, 0),
                                                dttm_deleted=dttm_now - datetime.timedelta(days=1))

        self.cashboxType4 = create_cashbox_type(self.shop, 'тип_кассы_4', id=4)

        self.cashbox1 = Cashbox.objects.create(
            type=self.cashboxType,
            number=1
        )

        self.cashbox2 = Cashbox.objects.create(
            type=self.cashboxType2,
            number=2
        )

        self.cashbox3 = Cashbox.objects.create(
            type=self.cashboxType,
            dttm_deleted=dttm_now - datetime.timedelta(days=3),
            number=3
        )

        for i in range(4, 10):
            Cashbox.objects.create(
                type=self.cashboxType3,
                number=i
            )

        create_period_demand(dttm_now, 10, 50, 1, 4, 3, self.cashboxType)
        create_period_demand(datetime.datetime(2018, 5, 10, 0, 0), 10, 50, 1, 4, 3, self.cashboxType)
        create_period_demand(datetime.datetime(2018, 6, 18, 7, 30), 100, 50, 1, 4, 3, self.cashboxType)
        create_period_demand(datetime.datetime(2018, 6, 18, 7, 30), 101, 23, 1, 4, 3, self.cashboxType)
        create_period_demand(datetime.datetime(2018, 6, 18, 7, 30), 10, 50, 1, 4, 3, self.cashboxType2)
        create_period_demand(datetime.datetime(2018, 5, 6, 0, 0), 10, 50, 1, 4, 3, self.cashboxType)

        for i in range(1, 20):
            self.worker_day1 = create_work_day(self.shop.id, self.user1, dt=datetime.datetime(2018, 6, i))
            self.worker_day2 = create_work_day(self.shop.id, self.user2, dt=datetime.datetime(2018, 6, i))
            self.worker_day3 = create_work_day(self.shop.id, self.user3, dt=datetime.datetime(2018, 6, i))

            WorkerDayCashboxDetails.objects.create(worker_day=self.worker_day1,
                                                   on_cashbox=self.cashbox1,
                                                   cashbox_type=self.cashboxType,
                                                   is_tablet=True,
                                                   tm_from=datetime.time(9, 0, 0),
                                                   tm_to=datetime.time(18, 0, 0),
                                                   )

            WorkerDayCashboxDetails.objects.create(worker_day=self.worker_day2,
                                                   on_cashbox=self.cashbox1,
                                                   cashbox_type=self.cashboxType,
                                                   is_tablet=True,
                                                   tm_from=(dttm_now - datetime.timedelta(hours=3)).time(),
                                                   tm_to=(dttm_now + datetime.timedelta(hours=3)).time()
                                                   )

        self.worker_day = create_work_day(self.shop.id, self.user1, dt=dttm_now.date())
        self.worker_day2 = create_work_day(self.shop.id, self.user2, dt=dttm_now.date())
        self.worker_day3 = create_work_day(self.shop.id, self.user3, dt=dttm_now.date())

        WorkerDayCashboxDetails.objects.create(worker_day=self.worker_day, on_cashbox=self.cashbox1, is_tablet=True,
                                               cashbox_type=self.cashboxType, tm_to=None,
                                               tm_from=(dttm_now - datetime.timedelta(hours=3)).time(),
                                               )

        self.cameracashbox = CameraCashbox.objects.create(name='Camera_1', cashbox=self.cashbox1)
        # self.cameracashbox10 = CameraCashbox.objects.create(name='Camera_3', cashbox=self.cashbox4)
        test_time = dttm_now
        for i in range(1, 20):
            create_camera_cashbox_stat(self.cameracashbox, test_time, i)
            test_time -= datetime.timedelta(seconds=10)



    def test_get_cashboxes_info(self):
        self.auth()
        response = self.api_get('/api/tablet/get_cashboxes_info?shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['1']['with_queue'], True)
        self.assertEqual(response.json['data']['1']['cashbox'][0]['number'], 1)
        self.assertEqual(response.json['data']['1']['cashbox'][0]['status'], 'O')
        self.assertEqual(response.json['data']['1']['cashbox'][0]['queue'], 5.5)
        self.assertEqual(response.json['data']['1']['cashbox'][0]['user_id'], '1')

    def test_get_cashiers_info(self):
        self.auth()
        response = self.api_get('/api/tablet/get_cashiers_info?shop_id=1&dttm={}'
                                .format(BaseConverter.convert_datetime(now() + datetime.timedelta(hours=3))))

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
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 400)
        self.assertEqual(response.json['data']['error_message'], 'cashbox 1 already opened')

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

        # print('\n\n\n\n', response, response.json, '\n\n\n\n')





    def test_aggr(self):
        from src.db.models import User,WorkerDay, WorkerMonthStat, ProductionMonth
        dt = now().date()
        import json
        from .utils import time_diff
        # hours = time_diff(tm_from, tm_to)
        last_user_id = ''
        work_hours = 0
        work_days = 0
        # product_month = ProductionMonth.objects.filter(
        #     # dt_first=datetime.date(year=dt.year, month=dt.month, day=1)
        # )
        product_month = ProductionMonth.objects.all().order_by('dt_first')
        for i in product_month:
            print(i.id, i.dt_first, i.total_days, i.norm_work_days, i.norm_work_hours)
        # shops = Shop.objects.all()
        # for shop in shops:
        #     print(shop.title)
        #
        #     status = WorkerDay.objects.select_related('worker').filter(
        #         worker_shop=shop,
        #         dt__lt=datetime.date(year=dt.year, month=dt.month, day=1),
        #         dt__gte=datetime.date(year=dt.year, month=dt.month-2, day=1),
        #     ).order_by('worker')
        #
        #     break_triplets = shop.break_triplets
        #     list_of_break_triplets = json.loads(break_triplets)
        #     for item in status:
        #         print(item.worker.username)
        #         time_break_triplets = 0
        #         duration_of_workerday = round(time_diff(item.tm_work_start, item.tm_work_end) / 60)
        #
        #         for triplet in list_of_break_triplets:
        #             if float(triplet[0]) < duration_of_workerday <= float(triplet[1]):
        #
        #                 for time_triplet in triplet[2]:
        #                     time_break_triplets += time_triplet
        #         duration_of_workerday -= time_break_triplets
        #         if last_user_id:
        #             if last_user_id == item.worker.id:
        #                 work_hours += duration_of_workerday
        #                 work_days += 1
        #                 print(duration_of_workerday)
        #             else:
        #                 print('===========', last_user_id, work_hours, work_days)
        #                 # пишем в базу и обнуляем
        #                 WorkerMonthStat.objects.update_or_create(
        #                     worker=last_user_id,
        #
        #                 )
        #                 work_hours = duration_of_workerday
        #                 work_days = 1
        #         else:
        #             work_hours = duration_of_workerday
        #             work_days = 1
        #         # print('duration_of_work', duration_of_workerday,  time_break_triplets)
        #         last_user_id = item.worker.id
        #     print('===========', last_user_id, work_hours, work_days)
        #     last_user_id = ''
        #     work_hours = 0
        #     work_days = 0
        #     # пишем в базу
