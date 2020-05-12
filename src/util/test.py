import datetime
from contextlib import contextmanager
from typing import TypeVar

from dateutil.relativedelta import relativedelta
from django.db import connection
from django.test import TestCase
from django.utils.timezone import now
from requests import Response
from etc.scripts import fill_calendar

from src.base.models import (
    Employment,
    FunctionGroup,
    Group,
    Region,
    Shop,
    User,
)
from src.timetable.models import (
    AttendanceRecords,
    Cashbox,
    Slot,
    ShopMonthStat,
    WorkerDayCashboxDetails,
    EmploymentWorkType,
    WorkType,
    WorkTypeName,
    WorkerDay,
    UserWeekdaySlot
)
from src.forecast.models import (
    OperationType,
    PeriodClients,
    OperationTypeName,
)


class LocalTestCaseAsserts(TestCase):
    def assertResponseCodeEqual(self, response: Response, code: int):
        got = response.json()['code']
        self.assertEqual(got, code, f"Got response code {got}, expected {code}: {response.json()}")

    def assertResponseDataListCount(self, response: Response, cnt: int):
        got = len(response.json()['data'])
        self.assertEqual(got, cnt, f"Got response data size {got}, expected {cnt}")

    def assertErrorType(self, response: Response, error_type: str):
        type_got = response.json()['data'].get('error_type')
        self.assertIsNotNone(type_got, "There is no error_type in response")
        self.assertEqual(type_got, error_type, f"Got error_type {type_got}, expected {error_type}")


class LocalTestCase(LocalTestCaseAsserts, TestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self, worker_day=False, calendar=False):
        super().setUp()
        # logging.disable(logging.CRITICAL)

        # Restart sequences from high value to not catch AlreadyExists errors on normal objects creation
        # TODO: remove explicit object ids in object.create-s below and this sequence restart
        with connection.cursor() as cursor:
            cursor.execute("ALTER SEQUENCE base_user_id_seq RESTART WITH 100;")

        dttm_now = now()

        create_departments_and_users(self)

        if calendar:
            fill_calendar.main('2018.1.1', (datetime.datetime.now() + datetime.timedelta(days=365)).strftime('%Y.%m.%d'), region_id=1)

        # work_types
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
        )
        self.work_type_name2 = WorkTypeName.objects.create(
            name='Тип_кассы_2',
        )
        self.work_type_name3 = WorkTypeName.objects.create(
            name='Тип_кассы_3',
        )
        self.work_type_name4 = WorkTypeName.objects.create(
            name='тип_кассы_4',
        )
        self.work_type1 = create_work_type(
            self.shop,
            self.work_type_name1,
            dttm_last_update_queue=dttm_now.replace(hour=0,minute=0,second=0,microsecond=0)
        )
        self.work_type2 = create_work_type(
            self.shop,
            self.work_type_name2,
            dttm_last_update_queue=dttm_now.replace(hour=0,minute=0,second=0,microsecond=0)
        )
        self.work_type3 = create_work_type(
            self.shop,
            self.work_type_name3,
            dttm_last_update_queue=None,
            dttm_deleted=dttm_now - datetime.timedelta(days=1)
        )
        self.work_type4 = create_work_type(self.shop2, self.work_type_name4)
        WorkType.objects.update(dttm_added=datetime.datetime(2018, 1, 1, 9, 0, 0))

        self.operation_type_name = OperationTypeName.objects.create(
            name='Test',
        )
        self.operation_type_name2 = OperationTypeName.objects.create(
            name='Test2',
        )
        self.operation_type_name3 = OperationTypeName.objects.create(
            name='Test3',
        )
        self.operation_type_name4 = OperationTypeName.objects.create(
            name='Test4',
        )

        create_operation_type(OperationType.FORECAST, [
            self.operation_type_name,
            self.operation_type_name2,
            self.operation_type_name3,
            self.operation_type_name4,
            ]
        )

        # cashboxes
        self.cashbox1 = Cashbox.objects.create(
            type=self.work_type1,
            name=1,
            id=1,
        )
        self.cashbox2 = Cashbox.objects.create(
            type=self.work_type2,
            name=2,
            id=2,
        )
        self.cashbox3 = Cashbox.objects.create(
            type=self.work_type3,
            dttm_deleted=dttm_now - datetime.timedelta(days=3),
            name=3,
            id=3,
        )
        for i in range(4, 10):
            Cashbox.objects.create(
                type=self.work_type4,
                name=i,
                id=i,
            )
        Cashbox.objects.update(dttm_added=datetime.datetime(2018, 1, 1, 8, 30, 0))

        # CameraGates
        # self.entry_gate = CameraClientGate.objects.create(type=CameraClientGate.TYPE_ENTRY, name='Вход')
        # self.exit_gate = CameraClientGate.objects.create(type=CameraClientGate.TYPE_OUT, name='Выход')

        # if periodclients:
        #
        #     # PeriodClients
        #     dttm_from = (dttm_now - relativedelta(days=15)).replace(hour=6, minute=30, second=0, microsecond=0)
        #     dttm_to = dttm_from + relativedelta(months=1)
        #     operation_types = OperationType.objects.all()
        #     while dttm_from < dttm_to:
        #         create_period_clients(
        #             dttm_forecast=dttm_from,
        #             value=randint(50, 150),
        #             type=PeriodClients.LONG_FORECASE_TYPE,
        #             operation_type=operation_types[0]
        #         )
        #         create_period_clients(
        #             dttm_forecast=dttm_from,
        #             value=randint(50, 150),
        #             type=PeriodClients.LONG_FORECASE_TYPE,
        #             operation_type=operation_types[1]
        #         )
        #         create_period_clients(
        #             dttm_forecast=dttm_from,
        #             value=randint(50, 150),
        #             type=PeriodClients.LONG_FORECASE_TYPE,
        #             operation_type=operation_types[2]
        #         )
        #         create_period_clients(
        #             dttm_forecast=dttm_from - relativedelta(months=1),
        #             value=randint(50, 150),
        #             type=PeriodClients.FACT_TYPE,
        #             operation_type=operation_types[3]
        #         )
        #         dttm_from += datetime.timedelta(minutes=30)
        #
        if worker_day:
            # Timetable
            dt_from = (dttm_now - relativedelta(days=15)).date()
            dt_to = dt_from + relativedelta(months=1)
            while dt_from < dt_to:
                for employment in Employment.objects.all():
                    self.create_worker_day(
                        employment=employment,
                        dt=dt_from,
                        dttm_work_start=datetime.datetime.combine(dt_from, datetime.time(9, 0)),
                        dttm_work_end=datetime.datetime.combine(dt_from, datetime.time(18, 0)),
                    )
                dt_from += datetime.timedelta(days=1)

        # Timetable create
        self.timetable1 = ShopMonthStat.objects.create(
            shop = self.shop,
            dt = datetime.date(2019, 6, 1),
            status = ShopMonthStat.READY,
            dttm_status_change=datetime.datetime(2019, 6, 1, 9, 30, 0)
        )
        # AttendanceRecords
        self.attendanShopMonthStat = AttendanceRecords.objects.create(
            dttm=datetime.datetime(2019, 6, 1, 9, 0, 0),
            type='C',
            user=self.user1,
            shop=self.shop
        )

        # CameraCashbox
        # self.camera_cashbox = CameraCashbox.objects.create(name='Camera_1', cashbox=self.cashbox1)

        # CameraCashboxStat
        # test_time = dttm_now
        # for i in range(1, 20):
        #     create_camera_cashbox_stat(self.camera_cashbox, test_time - datetime.timedelta(minutes=30 * i), i)
        #     test_time -= datetime.timedelta(seconds=10)

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
        EmploymentWorkType.objects.create(
            employment=self.employment1,
            work_type=self.work_type1,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=self.work_type3,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment3,
            work_type=self.work_type2,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment4,
            work_type=self.work_type1,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment5,
            work_type=self.work_type3,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment6,
            work_type=self.work_type1,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment7,
            work_type=self.work_type1,
        )

        # CameraClientEvent
        # gates = [self.exit_gate, self.entry_gate]
        # for i in range(15):
        #     CameraClientEvent.objects.create(
        #         dttm=dttm_now - datetime.timedelta(minutes=2 * i),
        #         gate=gates[i % 2],
        #         type=CameraClientEvent.DIRECTION_TYPES[i % 2][0],  # TOWARD / BACKWARD
        #     )

    def auth(self):
        self.client.post(
            '/api/auth/signin',
            {
                'username': self.USER_USERNAME,
                'password': self.USER_PASSWORD
            }
        )

    @contextmanager
    def auth_user(self, user=None):
        """Context manager to make requests as specified user logged in"""
        if user is None:
            user = self.user1
        self.client.force_login(user)
        yield user
        self.client.logout()

    def api_get(self, *args, **kwargs) -> Response:
        response = self.client.get(*args, **kwargs)
        return response

    def api_post(self, *args, **kwargs) -> Response:
        response = self.client.post(*args, **kwargs)
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
                    type=WorkerDay.TYPE_WORKDAY,
                    dt=dt,
                    worker=user
                )
                cashbox = active_cashboxes.order_by('?').first()
                WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    work_type=cashbox.type,
                )
                dt += datetime.timedelta(days=1)

    @staticmethod
    def refresh_model(item: TypeVar) -> TypeVar:
        """Re-fetch provided item from database"""
        return item.__class__.objects.get(pk=item.pk)


    def create_worker_day(
            self,
            employment,
            dt,
            dttm_work_start,
            dttm_work_end,
            type=WorkerDay.TYPE_WORKDAY
    ):
        worker_day = WorkerDay.objects.create(
            employment=employment,
            worker=employment.user,
            shop=employment.shop,
            type=type,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
        )
        cashbox = self.cashbox3
        WorkerDayCashboxDetails.objects.create(
            worker_day=worker_day,
            work_type=cashbox.type,
        )
        return worker_day


def create_departments_and_users(self):
    dt = now().date() - relativedelta(months=1)

    self.region = Region.objects.create(
        id=1,
        name='Москва',
        code=77,
    )
    # admin_group
    self.admin_group = Group.objects.create(name='Администратор')
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=self.admin_group,
            func=func,
            level_up=1,
            level_down=99,
            # access_type=FunctionGroup.TYPE_ALL
        ) for func in FunctionGroup.FUNCS
    ])

    # # central office
    # self.hq_group = Group.objects.create(name='ЦО')
    # for func in FunctionGroup.FUNCS:
    #     if 'get' in func or func == 'signin' or func == 'signout':
    #         FunctionGroup.objects.create(
    #             group=self.hq_group,
    #             func=func,
    #             level_up=1,
    #             level_down=99,
    #             # access_type =FunctionGroup.TYPE_ALL
    #         )

    # chiefs
    self.chief_group = Group.objects.create(name='Руководитель')
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=self.chief_group,
            func=func,
            level_up=0,
            level_down=99,
            # access_type=FunctionGroup.TYPE_SUPERSHOP
        ) for func in FunctionGroup.FUNCS
    ])

    # employee
    self.employee_group = Group.objects.create(name='Сотрудник')
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=self.employee_group,
            func=func,
            level_up=0,
            level_down=0,
            # access_type=FunctionGroup.TYPE_SELF
        ) for func in FunctionGroup.FUNCS
    ])

    Shop._tree_manager.rebuild()
    # supershop
    self.root_shop = Shop.objects.first()

    # shops
    self.reg_shop1 = Shop.objects.create(
        # id=11,
        parent=self.root_shop,
        name='Region Shop1',
        break_triplets=[[0, 360, [30]], [360, 540, [30, 30]], [540, 780, [30, 30, 15]]],
        tm_shop_opens=datetime.time(7, 0, 0),
        tm_shop_closes=datetime.time(0, 0, 0),
        region=self.region,
    )
    self.reg_shop2 = Shop.objects.create(
        # id=12,
        parent=self.root_shop,
        name='Region Shop2',
        tm_shop_opens=datetime.time(7, 0, 0),
        tm_shop_closes=datetime.time(0, 0, 0),
        region=self.region,
    )

    # shops
    self.shop = Shop.objects.create(
        # id=13,
        parent=self.reg_shop1,
        name='Shop1',
        break_triplets=[[0, 360, [30]], [360, 540, [30, 30]], [540, 780, [30, 30, 15]]],
        tm_shop_opens=datetime.time(7, 0, 0),
        tm_shop_closes=datetime.time(0, 0, 0),
        region=self.region,
    )
    self.shop2 = Shop.objects.create(
        # id=2,
        parent=self.reg_shop1,
        name='Shop2',
        tm_shop_opens=datetime.time(7, 0, 0),
        tm_shop_closes=datetime.time(0, 0, 0),
        region=self.region,
    )

    self.shop3 = Shop.objects.create(
        # id=3,
        parent=self.reg_shop2,
        name='Shop3',
        tm_shop_opens=datetime.time(7, 0, 0),
        tm_shop_closes=datetime.time(0, 0, 0),
        region=self.region,
    )
    Shop.objects.rebuild()

    # users
    self.user1 = User.objects.create_user(
        self.USER_USERNAME,
        self.USER_EMAIL,
        self.USER_PASSWORD,
        id=1,
        last_name='Васнецов',
        first_name='Иван',
    )
    self.employment1 = Employment.objects.create(
        user=self.user1,
        shop=self.root_shop,
        function_group=self.admin_group,
    )
    self.user2 = User.objects.create_user(
        'user2',
        'u2@b.b',
        '4242',
        id=2,
        first_name='Иван2',
        last_name='Иванов')
    self.employment2 = Employment.objects.create(
        user=self.user2,
        shop=self.shop,
        function_group=self.employee_group,
        dt_hired=dt,
        salary=100,
    )
    self.user3 = User.objects.create_user(
        'user3',
        'u3@b.b',
        '4242',
        id=3,
        first_name='Иван3',
        last_name='Сидоров',
    )
    self.employment3 = Employment.objects.create(
        user=self.user3,
        shop=self.shop,
        auto_timetable=False,
        function_group=self.employee_group,
        dt_hired=dt,
        salary=150
    )

    self.user4 = User.objects.create_user(
        'user4',
        '4b@b.b',
        '4242',
        id=4,
        last_name='Петров',
        first_name='Иван4',
    )
    self.employment4 = Employment.objects.create(
        user=self.user4,
        shop=self.shop,
        function_group=self.admin_group,
    )

    self.user5 = User.objects.create_user(
        'user5',
        'm@m.m',
        '4242',
        id=5,
        last_name='Васнецов5',
        first_name='Иван5',
    )
    self.employment5 = Employment.objects.create(
        user=self.user5,
        shop=self.reg_shop1,
        function_group=self.chief_group,
    )

    self.user6 = User.objects.create_user(
        'user6',
        'b@b.b',
        '4242',
        id=6,
        last_name='Васнецов6',
        first_name='Иван6',
    )
    self.employment6 = Employment.objects.create(
        user=self.user6,
        shop=self.shop,
        function_group=self.chief_group,
    )

    self.user7 = User.objects.create_user(
        'user7',
        'k@k.k',
        '4242',
        id=7,
        last_name='Васнецов7',
        first_name='Иван7',
    )
    self.employment7 = Employment.objects.create(
        user=self.user7,
        shop=self.shop,
        function_group=self.employee_group,
    )

# def create_camera_cashbox_stat(camera_cashbox_obj, dttm, queue):
#     CameraCashboxStat.objects.create(
#         camera_cashbox=camera_cashbox_obj,
#         dttm=dttm,
#         queue=queue,
#     )


def create_work_type(shop, name, dttm_last_update_queue=None, dttm_deleted=None):
    work_type = WorkType.objects.create(
        shop=shop,
        work_type_name=name,
        dttm_deleted=dttm_deleted,
        dttm_last_update_queue=dttm_last_update_queue
    )
    return work_type


def create_operation_type(do_forecast, operation_type_names, dttm_deleted=None):
    for i, work_type in enumerate(WorkType.objects.all()):
        OperationType.objects.create(
            operation_type_name=operation_type_names[i],
            work_type=work_type,
            do_forecast=do_forecast,
            dttm_deleted=dttm_deleted,
            shop=work_type.shop,
        )


def create_period_clients(dttm_forecast, value, type, operation_type):
    PeriodClients.objects.create(
        dttm_forecast=dttm_forecast,
        value=value,
        type=type,
        operation_type=operation_type
)
