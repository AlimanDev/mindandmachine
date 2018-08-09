import json
from django.test import TestCase
from src.db.models import User, WorkerDay, CameraCashboxStat, CashboxType, PeriodDemand, ProductionMonth
import datetime


class LocalTestCase(TestCase):
    USER_USERNAME = "u_1_1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(self.USER_USERNAME, self.USER_EMAIL, self.USER_PASSWORD, id=11)
        self.user2 = User.objects.create_user('f', self.USER_EMAIL, self.USER_PASSWORD, id=12)

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


def create_work_day(worker_shop_id, worker, dt):
    worker_day = WorkerDay.objects.create(
        worker_shop_id=worker_shop_id,
        worker=worker,
        type=2,
        dt=dt,
        tm_work_start=datetime.time(hour=12, minute=0, second=0),
        tm_work_end=datetime.time(hour=23, minute=0, second=0)
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
