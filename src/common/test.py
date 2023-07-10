import datetime, uuid, logging, warnings
from contextlib import contextmanager
from typing import TypeVar
from unittest import mock

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import connection
from django.db.models import Value, F, CharField
from django.db.models.functions import Concat
from django.test import TestCase
from django.test.runner import DiscoverRunner
from django.utils.timezone import now
from requests import Response

from etc.scripts import fill_calendar
from src.apps.base.models import (
    Employment,
    FunctionGroup,
    Group,
    Region,
    Shop,
    ShopSettings,
    User,
    Network,
    NetworkConnect,
    Break,
    Employee,
)
from src.apps.forecast.models import (
    OperationType,
    PeriodClients,
    OperationTypeName,
)
from src.apps.timetable.models import (
    AttendanceRecords,
    Slot,
    ShopMonthStat,
    EmploymentWorkType,
    WorkType,
    WorkTypeName,
    UserWeekdaySlot,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from src.apps.recognition.models import TickPhoto


class TestRunner(DiscoverRunner):
    """Custom test runner. Put all general mocks/fixes here."""
    @mock.patch.object(User, 'compress_image', lambda _: True)
    @mock.patch.object(TickPhoto, 'compress_image', lambda _: True)
    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        logging.disable(settings.TEST_LOG_LEVEL)   # Don't show logging messages
        warnings.filterwarnings("ignore")          # Don't show warnings
        return super().run_tests(test_labels, extra_tests, **kwargs)


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
            network=self.network,
        )
        self.work_type_name2 = WorkTypeName.objects.create(
            name='Тип_кассы_2',
            network=self.network,
        )
        self.work_type_name3 = WorkTypeName.objects.create(
            name='Тип_кассы_3',
            network=self.network,
        )
        self.work_type_name4 = WorkTypeName.objects.create(
            name='тип_кассы_4',
            network=self.network,
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
            network=self.network,
        )
        self.operation_type_name2 = OperationTypeName.objects.create(
            name='Test2',
            network=self.network,
        )
        self.operation_type_name3 = OperationTypeName.objects.create(
            name='Test3',
            network=self.network,
        )
        self.operation_type_name4 = OperationTypeName.objects.create(
            name='Test4',
            network=self.network,
        )

        create_operation_type(OperationType.FORECAST, [
            self.operation_type_name,
            self.operation_type_name2,
            self.operation_type_name3,
            self.operation_type_name4,
            ]
        )

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
            '/tevian/auth/signin',
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

    @staticmethod
    def refresh_model(item: TypeVar) -> TypeVar:
        """Re-fetch provided item from database"""
        return item.__class__.objects.get(pk=item.pk)


def create_departments_and_users(self, dt=None):
    dt = dt or now().date() - relativedelta(months=1)
    self.network, _n_created = Network.objects.get_or_create(code='default', defaults=dict(name='По умолчанию'))
    self.region, _r_created = Region.objects.update_or_create(
        id=1,
        defaults=dict(
            network=self.network,
            name='Москва',
            code='77',
        ),
    )
    # admin_group
    self.admin_group = Group.objects.create(name='Администратор', code='admin', network=self.network)
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=self.admin_group,
            method=method,
            func=func,
            level_up=1,
            level_down=99,
            # access_type=FunctionGroup.TYPE_ALL
        ) for func, _ in FunctionGroup.FUNCS_TUPLE for method, _ in FunctionGroup.METHODS_TUPLE
    ])
    GroupWorkerDayPermission.objects.bulk_create(
        GroupWorkerDayPermission(
            group=self.admin_group,
            worker_day_permission=wdp,
        ) for wdp in WorkerDayPermission.objects.all()
    )

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
    self.chief_group = Group.objects.create(name='Руководитель', code='director', network=self.network)
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=self.chief_group,
            func=func,
            level_up=0,
            level_down=99,
            # access_type=FunctionGroup.TYPE_SUPERSHOP
        ) for func, _ in FunctionGroup.FUNCS_TUPLE
    ])
    GroupWorkerDayPermission.objects.bulk_create(
        GroupWorkerDayPermission(
            group=self.chief_group,
            worker_day_permission=wdp,
        ) for wdp in WorkerDayPermission.objects.all()
    )

    # employee
    self.employee_group = Group.objects.create(name='Сотрудник', code='worker', network=self.network)
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=self.employee_group,
            func=func,
            level_up=0,
            level_down=0,
            # access_type=FunctionGroup.TYPE_SELF
        ) for func, _ in FunctionGroup.FUNCS_TUPLE
    ])
    self.admin_group.subordinates.add(self.admin_group, self.chief_group, self.employee_group)

    Shop._tree_manager.rebuild()
    # supershop
    self.root_shop = Shop.objects.first()
    self.root_shop.network = self.network
    self.root_shop.save()

    self.breaks = Break.objects.create(
        name='Default',
        network=self.network,
        value='[[0, 360, [30]], [360, 540, [30, 30]], [540, 1020, [30, 30, 15]]]'
    )

    self.shop_settings = ShopSettings.objects.create(
        breaks=self.breaks,
        network=self.network,
    )
    # shops
    self.reg_shop1 = Shop.objects.create(
        # id=11,
        parent=self.root_shop,
        name='Region Shop1',
        # break_triplets=[[0, 360, [30]], [360, 540, [30, 30]], [540, 780, [30, 30, 15]]],
        tm_open_dict='{"all":"07:00:00"}',
        tm_close_dict='{"all":"23:00:00"}',
        # tm_shop_opens=datetime.time(7, 0, 0),
        # tm_shop_closes=datetime.time(0, 0, 0),
        region=self.region,
        settings=self.shop_settings,
        network=self.network,
    )
    self.reg_shop2 = Shop.objects.create(
        # id=12,
        parent=self.root_shop,
        name='Region Shop2',
        tm_open_dict='{"all":"07:00:00"}',
        tm_close_dict='{"all":"00:00:00"}',
        region=self.region,
        settings=self.shop_settings,
        network=self.network,
    )

    # shops
    self.shop = Shop.objects.create(
        # id=13,
        parent=self.reg_shop1,
        name='Shop1',
        # break_triplets=[[0, 360, [30]], [360, 540, [30, 30]], [540, 780, [30, 30, 15]]],
        tm_open_dict='{"all":"07:00:00"}',
        tm_close_dict='{"all":"00:00:00"}',
        region=self.region,
        settings=self.shop_settings,
        network=self.network,
    )
    self.shop2 = Shop.objects.create(
        # id=2,
        parent=self.reg_shop1,
        name='Shop2',
        tm_open_dict='{"all":"07:00:00"}',
        tm_close_dict='{"all":"00:00:00"}',
        region=self.region,
        settings=self.shop_settings,
        network=self.network,
    )

    self.shop3 = Shop.objects.create(
        # id=3,
        parent=self.reg_shop2,
        name='Shop3',
        tm_open_dict='{"all":"07:00:00"}',
        tm_close_dict='{"all":"00:00:00"}',
        region=self.region,
        settings=self.shop_settings,
        network=self.network,
    )
    Shop.objects.rebuild()

    # users
    self.user1 = User.objects.create_user(
        self.USER_USERNAME,
        self.USER_EMAIL,
        self.USER_PASSWORD,
        last_name='Васнецов',
        first_name='Иван',
        network=self.network,
    )

    self.employee1 = Employee.objects.create(user=self.user1)
    self.employment1 = Employment.objects.create(
        code=f'{self.user1.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee1,
        shop=self.root_shop,
        function_group=self.admin_group,
    )
    self.user2 = User.objects.create_user(
        'user2',
        'u2@b.b',
        '4242',
        first_name='Иван2',
        last_name='Иванов',
        network=self.network,
    )
    self.employee2 = Employee.objects.create(user=self.user2, tabel_code='employee2_tabel_code')
    self.employment2 = Employment.objects.create(
        code=f'{self.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee2,
        shop=self.shop,
        function_group=self.employee_group,
        salary=100,
    )
    self.user3 = User.objects.create_user(
        'user3',
        'u3@b.b',
        '4242',
        first_name='Иван3',
        last_name='Сидоров',
        network=self.network,
    )
    self.employee3 = Employee.objects.create(user=self.user3)
    self.employment3 = Employment.objects.create(
        code=f'{self.user3.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee3,
        shop=self.shop,
        auto_timetable=False,
        function_group=self.employee_group,
        salary=150,
    )

    self.user4 = User.objects.create_user(
        'user4',
        '4b@b.b',
        '4242',
        last_name='Петров',
        first_name='Иван4',
        network=self.network,
    )
    self.employee4 = Employee.objects.create(user=self.user4)
    self.employment4 = Employment.objects.create(
        code=f'{self.user4.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee4,
        shop=self.shop,
        function_group=self.admin_group,
    )

    self.user5 = User.objects.create_user(
        'user5',
        'm@m.m',
        '4242',
        last_name='Васнецов5',
        first_name='Иван5',
        network=self.network,
    )
    self.employee5 = Employee.objects.create(user=self.user5)
    self.employment5 = Employment.objects.create(
        code=f'{self.user5.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee5,
        shop=self.reg_shop1,
        function_group=self.chief_group,
    )

    self.user6 = User.objects.create_user(
        'user6',
        'b@b.b',
        '4242',
        last_name='Васнецов6',
        first_name='Иван6',
        network=self.network,
    )
    self.employee6 = Employee.objects.create(user=self.user6)
    self.employment6 = Employment.objects.create(
        code=f'{self.user6.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee6,
        shop=self.shop,
        function_group=self.chief_group,
    )

    self.user7 = User.objects.create_user(
        'user7',
        'k@k.k',
        '4242',
        last_name='Васнецов7',
        first_name='Иван7',
        network=self.network,
    )
    self.employee7 = Employee.objects.create(user=self.user7)
    self.employment7 = Employment.objects.create(
        code=f'{self.user7.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee7,
        shop=self.shop,
        function_group=self.employee_group,
    )
    self.user8 = User.objects.create_user(
        'user8',
        'k@k.k',
        '4242',
        last_name='Васнецов8',
        first_name='Иван8',
        network=self.network,
    )
    self.employee8 = Employee.objects.create(user=self.user8)
    self.employment8 = Employment.objects.create(
        code=f'{self.user8.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee8,
        shop=self.shop2,
        function_group=self.employee_group,
    )
    self.employment8_old = Employment.objects.create(
        dt_hired=dt - datetime.timedelta(days=900),
        dt_fired=dt - datetime.timedelta(days=700),
        code=f'{self.user8.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee8,
        shop=self.shop2,
        function_group=self.employee_group,
    )
    Shop.objects.all().update(code=Concat(Value('code-', output_field=CharField()), F('id')), network=self.network)
    for s in [self.root_shop, self.shop, self.shop2, self.shop3, self.reg_shop1, self.reg_shop2]:
        s.refresh_from_db()

def create_outsource(self, dt=None):
    if not hasattr(self, 'network'):
        raise Exception('create_outsource called before create_departments_and_users')

    dt = dt or now().date() - relativedelta(months=1)
    self.network_outsource = Network.objects.create(code='outsource', name='Аутсорс-сеть')
    NetworkConnect.objects.create(
        client=self.network,
        outsourcing=self.network_outsource,
        allow_assign_employements_from_outsource=True,
        allow_choose_shop_from_client_for_employement=True
    )
    self.region_outsource = Region.objects.create(
        network=self.network_outsource,
        name='Аутсорс-регион',
        code='outsource',
    )
    self.shop_outsource = Shop.objects.create(
        name='Аутсорс-магазин',
        network=self.network_outsource,
        region=self.region_outsource  
    )
    self.user1_outsource = User.objects.create_user(
        'user1_outsource',
        'user1_outsource@example.ru',
        'user1_outsource_password',
        first_name='Аут',
        last_name='Сорсович',
        network=self.network_outsource,
    )
    self.employee1_outsource = Employee.objects.create(user=self.user1_outsource)
    self.employment1_outsource = Employment.objects.create(
        code=f'{self.user1_outsource.username}:{uuid.uuid4()}:{uuid.uuid4()}',
        employee=self.employee1_outsource,
        shop=self.shop_outsource,
    )

    GroupWorkerDayPermission.objects.bulk_create(
        GroupWorkerDayPermission(
            group=self.admin_group,
            worker_day_permission=wdp,
            employee_type=GroupWorkerDayPermission.OTHER_SHOP_OR_NETWORK_EMPLOYEE,
        ) for wdp in WorkerDayPermission.objects.all()
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
        dt_report=dttm_forecast.date(),
        value=value,
        type=type,
        operation_type=operation_type
    )
