import json
from django.test import TestCase

from django.db.models import Q
from src.db.models import (
    User,
    WorkerDay,
    CameraCashboxStat,
    CashboxType,
    PeriodDemand,
    PeriodClients,
    Shop,
    SuperShop,
    Cashbox,
    CameraCashbox,
    WorkerDayCashboxDetails,
    Slot,
    UserWeekdaySlot,
    WorkerCashboxInfo,
    CameraClientGate,
    CameraClientEvent
)
from random import randint
import datetime
from dateutil.relativedelta import relativedelta
from django.utils.timezone import now


class LocalTestCase(TestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        dttm_now = now()

        # supershop
        self.superShop = SuperShop.objects.create(
            title='SuperShop1',
            tm_start=datetime.time(7, 0, 0),
            tm_end=datetime.time(0, 0, 0),
        )

        # shops
        self.shop = Shop.objects.create(
            id=1,
            super_shop=self.superShop,
            title='Shop1',
            break_triplets=[[0, 360, [30]], [360, 540, [30, 30]], [540, 780, [30, 30, 15]]]
        )
        self.shop2 = Shop.objects.create(
            id=2,
            super_shop=self.superShop,
            title='Shop2',
        )

        # users
        self.user1 = User.objects.create_user(
            self.USER_USERNAME,
            self.USER_EMAIL,
            self.USER_PASSWORD,
            id=1,
            shop=self.shop,
            last_name='Дурак',
            first_name='Иван',
            group=User.GROUP_SUPERVISOR
        )
        self.user2 = create_user(user_id=2, shop_id=self.shop, username='user2', first_name='Иван2', last_name='Иванов')
        self.user3 = create_user(user_id=3, shop_id=self.shop, username='user3', first_name='Иван3', last_name='Сидоров')
        self.user4 = create_user(
            user_id=4,
            shop_id=self.shop,
            username='user4',
            dt_fired=(dttm_now - datetime.timedelta(days=1)).date(),
            first_name='Иван4',
            last_name='Петров'
        )

        # cashbox_types
        self.cashbox_type1 = create_cashbox_type(
            self.shop,
            'Кассы',
            id=1,
            dttm_last_update_queue=datetime.datetime(2018, 12, 1, 8, 30, 0)
        )
        self.cashbox_type2 = create_cashbox_type(
            self.shop,
            'тип_кассы_2',
            id=2,
            dttm_last_update_queue=datetime.datetime(2018, 12, 1, 9, 0, 0)
        )
        self.cashbox_type3 = create_cashbox_type(
            self.shop,
            'тип_кассы_3',
            id=3,
            dttm_last_update_queue=None,
            dttm_deleted=dttm_now - datetime.timedelta(days=1)
        )
        self.cashbox_type4 = create_cashbox_type(self.shop2, 'тип_кассы_4', id=4)
        CashboxType.objects.update(dttm_added=datetime.datetime(2018, 1, 1, 9, 0, 0))

        # cashboxes
        self.cashbox1 = Cashbox.objects.create(
            type=self.cashbox_type1,
            number=1,
            id=1,
        )
        self.cashbox2 = Cashbox.objects.create(
            type=self.cashbox_type2,
            number=2,
            id=2,
        )
        self.cashbox3 = Cashbox.objects.create(
            type=self.cashbox_type3,
            dttm_deleted=dttm_now - datetime.timedelta(days=3),
            number=3,
            id=3,
        )
        for i in range(4, 10):
            Cashbox.objects.create(
                type=self.cashbox_type4,
                number=i,
                id=i,
            )
        Cashbox.objects.update(dttm_added=datetime.datetime(2018, 1, 1, 8, 30, 0))

        # CameraGates
        self.entry_gate = CameraClientGate.objects.create(type=CameraClientGate.TYPE_ENTRY, name='Вход')
        self.exit_gate = CameraClientGate.objects.create(type=CameraClientGate.TYPE_OUT, name='Выход')

        # PeriodClients
        dttm_from = (dttm_now - relativedelta(days=15)).replace(hour=6, minute=30, second=0, microsecond=0)
        dttm_to = dttm_from + relativedelta(months=1)
        while dttm_from < dttm_to:
            create_period_clients(
                dttm_forecast=dttm_from, value=randint(50, 150), type=PeriodClients.LONG_FORECASE_TYPE, cashbox_type=self.cashbox_type1
            )
            create_period_clients(
                dttm_forecast=dttm_from, value=randint(50, 150), type=PeriodClients.LONG_FORECASE_TYPE, cashbox_type=self.cashbox_type2
            )
            create_period_clients(
                dttm_forecast=dttm_from, value=randint(50, 150), type=PeriodClients.LONG_FORECASE_TYPE, cashbox_type=self.cashbox_type3
            )
            dttm_from += datetime.timedelta(minutes=30)

        # Timetable
        dt_from = (dttm_now - relativedelta(days=15)).date()
        dt_to = dt_from + relativedelta(months=1)
        while dt_from < dt_to:
            for user in User.objects.all():
                create_worker_day(
                    worker=user,
                    dt=dt_from,
                    dttm_work_start=datetime.datetime.combine(dt_from, datetime.time(9, 0)),
                    dttm_work_end=datetime.datetime.combine(dt_from, datetime.time(18, 0)),
                )
            dt_from += datetime.timedelta(days=1)

        # CameraCashbox
        self.camera_cashbox = CameraCashbox.objects.create(name='Camera_1', cashbox=self.cashbox1)

        # CameraCashboxStat
        test_time = dttm_now
        for i in range(1, 20):
            create_camera_cashbox_stat(self.camera_cashbox, test_time - datetime.timedelta(minutes=30*i), i)
            test_time -= datetime.timedelta(seconds=10)

        # Slots
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

        # UserWeekdaySlot
        UserWeekdaySlot.objects.create(
            weekday=0,
            slot=self.slot1,
            worker=self.user1,
            id=1
        )

        # WorkerCashboxInfo
        WorkerCashboxInfo.objects.create(
            id=1,
            worker=self.user1,
            cashbox_type=self.cashbox_type1,
        )
        WorkerCashboxInfo.objects.create(
            id=2,
            worker=self.user2,
            cashbox_type=self.cashbox_type3,
        )
        WorkerCashboxInfo.objects.create(
            id=3,
            worker=self.user3,
            cashbox_type=self.cashbox_type2,
        )
        WorkerCashboxInfo.objects.create(
            id=4,
            worker=self.user4,
            cashbox_type=self.cashbox_type1,
        )

        # CameraClientEvent
        gates = [self.exit_gate, self.entry_gate]
        for i in range(15):
            CameraClientEvent.objects.create(
                dttm=dttm_now - datetime.timedelta(minutes=2*i),
                gate=gates[i % 2],
                type=CameraClientEvent.DIRECTION_TYPES[i % 2][0],  # TOWARD / BACKWARD
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

    def create_many_users(self, amount, from_date, to_date):
        time_start = datetime.time(7, 0)
        time_end = datetime.time(1, 0)
        active_cashboxes = Cashbox.objects.qos_filter_active(from_date, to_date)
        for i in range(amount):
            user = User.objects.create(
                id=1000 + i,
                last_name='user_{}'.format(1000 + i),
                shop=self.shop,
                first_name='Иван',
                username='user_{}'.format(1000 + i),
            )
            dt = from_date
            while dt < to_date:
                wd = WorkerDay.objects.create(
                    dttm_work_start=datetime.datetime.combine(dt, time_start),
                    dttm_work_end=datetime.datetime.combine(dt + datetime.timedelta(days=1), time_end),
                    type=WorkerDay.Type.TYPE_WORKDAY.value,
                    dt=dt,
                    worker=user
                )
                cashbox = active_cashboxes.order_by('?').first()
                WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    on_cashbox=cashbox,
                    cashbox_type=cashbox.type,
                    dttm_from=wd.dttm_work_start,
                    dttm_to=wd.dttm_work_end,
                    is_tablet=True
                )
                dt += datetime.timedelta(days=1)


def create_user(user_id, shop_id, username, dt_hired=None, dt_fired=None, first_name='', last_name=''):
    user = User.objects.create(
        id=user_id,
        username=username,
        shop=shop_id,
        dt_hired=dt_hired,
        dt_fired=dt_fired,
        first_name=first_name,
        last_name=last_name,
    )
    return user


def create_worker_day(
    worker,
    dt,
    dttm_work_start,
    dttm_work_end,
    type=WorkerDay.Type.TYPE_WORKDAY.value
):
    worker_day = WorkerDay.objects.create(
        worker=worker,
        type=type,
        dt=dt,
        dttm_work_start=dttm_work_start,
        dttm_work_end=dttm_work_end,
    )
    cashbox = Cashbox.objects.all()[worker.id]
    WorkerDayCashboxDetails.objects.create(
        worker_day=worker_day,
        on_cashbox=cashbox,
        cashbox_type=cashbox.type,
        dttm_from=worker_day.dttm_work_start,
        dttm_to=worker_day.dttm_work_end,
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


def create_period_clients(dttm_forecast, value, type, cashbox_type):
    PeriodClients.objects.create(
        dttm_forecast=dttm_forecast,
        value=value,
        type=type,
        cashbox_type=cashbox_type
    )