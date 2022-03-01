from datetime import datetime, time, date, timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q

from django.test import override_settings

from django.utils.timezone import now
from rest_framework.test import APITestCase
from unittest.mock import patch, call

from src.timetable.models import WorkerDay, AttendanceRecords
from src.base.models import WorkerPosition, Employment
from src.integration.models import AttendanceArea, ExternalSystem, UserExternalCode, ShopExternalCode
from src.integration.tasks import import_urv_zkteco, export_workers_zkteco, delete_workers_zkteco
from src.timetable.tests.factories import WorkTypeFactory, WorkTypeNameFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.test import create_departments_and_users

dttm_first = datetime.combine(date.today(), time(10, 48))
dttm_second = datetime.combine(date.today(), time(12, 34))
dttm_third = datetime.combine(date.today(), time(15, 56))

default_transaction_response = {
    1:{
        "code": 0,
        "message": "success",
        "data": [
            {
                "id": "8a8080847322cd7f017323a7df9e0dc2",
                "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                "pin": "1",
                "name": "User",
                "lastName": "User",
                "deptName": "Area Name",
                "areaName": "Area Name",
                "devSn": "CGXH201360029",
                "verifyModeName": "15",
                "accZone": "1",
            },
        ],
    },
    2:{
        "code": 0,
        "message": "success",
        "data":[
            {
                "id": "8a8080847322cd7f017323a7df9e0dc3",
                "eventTime": dttm_third.strftime('%Y-%m-%d %H:%M:%S'),
                "pin": "1",
                "name": "User",
                "lastName": "User",
                "deptName": "Area Name",
                "areaName": "Area Name",
                "devSn": "CGXH201360029",
                "verifyModeName": "15",
                "accZone": "1",
            },
        ],
    },
    3:{
        "code": 0,
        "message": "success",
        "data":[
            {
                "id": "8a8080847322cd7f017323a7df9e0dc4",
                "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                "pin": "1",
                "name": "User",
                "lastName": "User",
                "deptName": "Area Name",
                "areaName": "Area Name",
                "devSn": "CGXH201360029",
                "verifyModeName": "15",
                "accZone": "1",
            },
        ],
    }
}

class TestRequestMock:
    responses = {
        "/transaction/listAttTransaction": default_transaction_response
    }
    
    def __init__(self, *args, **kwargs):
        pass

    def json(self):
        return self.response
    
    def request(self, method, url, params={}, json=None, data=None):
        if params.get('pageNo'):
            self.response = self.responses.get(url, {}).get(params.get('pageNo'), {"data": None})
        else:
            self.response = self.responses.get(url, {"code": 0})
        return self

    def raise_for_status(self):
        return None


@override_settings(
    ZKTECO_HOST='', 
    CELERY_TASK_ALWAYS_EAGER=True, 
    ZKTECO_INTEGRATION=True, 
    ZKTECO_KEY='1234', 
    ZKTECO_USER_ID_SHIFT=10000,
)
class TestIntegration(TestsHelperMixin, APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.dt = now().date()

        cls.create_departments_and_users()
        cls.ext_system, _ = ExternalSystem.objects.get_or_create(
            code='zkteco',
            defaults={
                'name':'ZKTeco',
            },
        )
        cls.position = WorkerPosition.objects.create(
            name='Должность',
            network=cls.network,
        )
        cls.att_area, _ = AttendanceArea.objects.update_or_create(
            code='1',
            external_system=cls.ext_system,
            defaults={
                'name': 'Тестовая зона',
            }
        )
        cls.att_area2, _ = AttendanceArea.objects.update_or_create(
            code='2',
            external_system=cls.ext_system,
            defaults={
                'name': 'Тестовая зона 2',
            }
        )

        Employment.objects.filter(
            shop=cls.shop,
        ).update(
            position=cls.position,
        )
        cls.employment1.position = cls.position

    def setUp(self):
        self.client.force_authenticate(user=self.user1)


    def test_export_workers(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            export_workers_zkteco()
        self.assertEqual(UserExternalCode.objects.count(), 5)

    
    def test_delete_workers(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            export_workers_zkteco()
            self.employment2.dt_fired = date.today() - timedelta(days=2)
            self.employment2.save()
            delete_workers_zkteco()
        self.assertEqual(UserExternalCode.objects.count(), 4)

    def test_delete_workers_many_shops_to_one_zone(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop2,
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            export_workers_zkteco()
            self.assertEqual(UserExternalCode.objects.count(), 5)
            self.employment2.dt_fired = date.today() - timedelta(days=2)
            self.employment2.save()
            Employment.objects.create(
                employee_id=self.employment2.employee_id,
                shop_id=self.shop2.id,
                position=self.position,
            )
            delete_workers_zkteco()
        self.assertEqual(UserExternalCode.objects.count(), 5)
    
    def test_delete_workers_many_shops_to_one_user(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area2,
            shop=self.shop2,
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            export_workers_zkteco()
            self.assertEqual(UserExternalCode.objects.count(), 5)
            self.employment2.dt_fired = date.today() - timedelta(days=2)
            self.employment2.save()
            Employment.objects.create(
                employee_id=self.employment2.employee_id,
                shop_id=self.shop2.id,
                position=self.position,
            )
            delete_workers_zkteco()
        self.assertEqual(UserExternalCode.objects.count(), 5)
    
    def test_import_urv(self):
        TestRequestMock.responses["/transaction/listAttTransaction"] = default_transaction_response
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(10)),
            dttm_work_end=datetime.combine(date.today(), time(20)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today() - timedelta(1),
            dttm_work_start=datetime.combine(date.today() - timedelta(1), time(10)),
            dttm_work_end=datetime.combine(date.today() - timedelta(1), time(20)),
            is_approved=True,
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_third)

    def test_import_urv_night_shift(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(10)),
            dttm_work_end=datetime.combine(date.today(), time(20)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today() - timedelta(1),
            dttm_work_start=datetime.combine(date.today() - timedelta(1), time(18)),
            dttm_work_end=datetime.combine(date.today(), time(2)),
            is_approved=True,
        )
        dttm_first = datetime.combine(date.today() - timedelta(1), time(18, 48))
        dttm_second = datetime.combine(date.today(), time(2, 56))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
                1:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc3",
                            "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                2:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc4",
                            "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                }
        }
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_end, dttm_second)

    @override_settings(ZKTECO_IGNORE_TICKS_WITHOUT_WORKER_DAY=False)
    def test_import_urv_without_worker_day(self):
        TestRequestMock.responses["/transaction/listAttTransaction"] = default_transaction_response
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )

        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_third)

    @override_settings(ZKTECO_IGNORE_TICKS_WITHOUT_WORKER_DAY=False)
    def test_import_urv_multiple_arrivals_nearby_without_worker_day(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        dttm_first = datetime.combine(date.today(), time(12, 12))
        dttm_second = datetime.combine(date.today(), time(12, 13))
        dttm_third = datetime.combine(date.today(), time(20, 1))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
                1:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc3",
                            "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                2:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc4",
                            "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                3: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc5",
                            "eventTime": dttm_third.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                }
        }
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_third)

    def test_import_urv_night_shift_with_coming_record_refers_to_the_previous_date(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today() - timedelta(1),
            dttm_work_start=datetime.combine(date.today() - timedelta(1), time(23, 30)),
            dttm_work_end=datetime.combine(date.today(), time(7)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(23, 30)),
            dttm_work_end=datetime.combine(date.today() + timedelta(1), time(7)),
            is_approved=True,
        )


        dttm_first = datetime.combine(date.today(), time(0, 11))
        dttm_second = datetime.combine(date.today(), time(8, 12))
        dttm_third = datetime.combine(date.today(), time(23, 56))
        dttm_fourth = datetime.combine(date.today() + timedelta(1), time(7, 56))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
                1:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc1",
                            "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                2:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc2",
                            "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                3: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc3",
                            "eventTime": dttm_third.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                4: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc4",
                            "eventTime": dttm_fourth.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                }
        }
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 2)
        self.assertEqual(AttendanceRecords.objects.count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_end, dttm_second)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_third)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_fourth)

    def test_import_urv_night_shift_with_coming_record_refers_to_the_next_date(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today() - timedelta(1),
            dttm_work_start=datetime.combine(date.today() - timedelta(1), time(0, 30)),
            dttm_work_end=datetime.combine(date.today() - timedelta(1), time(9)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(0, 30)),
            dttm_work_end=datetime.combine(date.today(), time(9)),
            is_approved=True,
        )


        dttm_first = datetime.combine(date.today() - timedelta(2), time(23, 55))
        dttm_second = datetime.combine(date.today() - timedelta(1), time(8, 12))
        dttm_third = datetime.combine(date.today(), time(0, 23))
        dttm_fourth = datetime.combine(date.today(), time(8, 56))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
                1:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc1",
                            "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                2:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc2",
                            "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                3: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc3",
                            "eventTime": dttm_third.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                4: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc4",
                            "eventTime": dttm_fourth.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                }
        }
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 2)
        self.assertEqual(AttendanceRecords.objects.count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_end, dttm_second)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_third)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_fourth)

    def test_import_urv_night_shift_with_leaving_record_refers_to_the_previous_date(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today() - timedelta(1),
            dttm_work_start=datetime.combine(date.today() - timedelta(1), time(15)),
            dttm_work_end=datetime.combine(date.today() - timedelta(1), time(23, 30)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(15)),
            dttm_work_end=datetime.combine(date.today(), time(23, 30)),
            is_approved=True,
        )

        dttm_first = datetime.combine(date.today() - timedelta(1), time(16))
        dttm_second = datetime.combine(date.today(), time(0, 7))
        dttm_third = datetime.combine(date.today(), time(15, 11))
        dttm_fourth = datetime.combine(date.today(), time(23, 56))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
                1:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc1",
                            "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                2:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc2",
                            "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                3: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc3",
                            "eventTime": dttm_third.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                4: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc4",
                            "eventTime": dttm_fourth.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                }
        }
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 2)
        self.assertEqual(AttendanceRecords.objects.count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_end, dttm_second)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_third)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_fourth)

    def test_import_urv_night_shift_with_leaving_record_refers_to_the_next_date(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today() - timedelta(1),
            dttm_work_start=datetime.combine(date.today() - timedelta(1), time(15)),
            dttm_work_end=datetime.combine(date.today(), time(0, 30)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(15)),
            dttm_work_end=datetime.combine(date.today() + timedelta(1), time(0, 30)),
            is_approved=True,
        )

        dttm_first = datetime.combine(date.today() - timedelta(1), time(14))
        dttm_second = datetime.combine(date.today() - timedelta(1), time(23, 55))
        dttm_third = datetime.combine(date.today(), time(16, 11))
        dttm_fourth = datetime.combine(date.today() + timedelta(1), time(0, 25))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
                1:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc1",
                            "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                2:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc2",
                            "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                3: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc3",
                            "eventTime": dttm_third.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                4: {
                    "code": 0,
                    "message": "success",
                    "data": [
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc4",
                            "eventTime": dttm_fourth.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                }
        }
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 2)
        self.assertEqual(AttendanceRecords.objects.count(), 4)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today() - timedelta(1)).first().dttm_work_end, dttm_second)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_third)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_fourth)

    def test_import_urv_tick_in_middle_of_shift_with_bad_diff(self):
        self.network.max_plan_diff_in_seconds = 4*60*60
        self.network.save()
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='1',
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(10)),
            dttm_work_end=datetime.combine(date.today(), time(20)),
            is_approved=True,
        )

        dttm_first = datetime.combine(date.today(), time(9, 15))
        dttm_second = datetime.combine(date.today(), time(14, 40))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
                1:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc1",
                            "eventTime": dttm_second.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
                2:{
                    "code": 0,
                    "message": "success",
                    "data":[
                        {
                            "id": "8a8080847322cd7f017323a7df9e0dc2",
                            "eventTime": dttm_first.strftime('%Y-%m-%d %H:%M:%S'),
                            "pin": "1",
                            "name": "User",
                            "lastName": "User",
                            "deptName": "Area Name",
                            "areaName": "Area Name",
                            "devSn": "CGXH201360029",
                            "verifyModeName": "15",
                            "accZone": "1",
                        },
                    ],
                },
        }
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_start, dttm_first)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today()).first().dttm_work_end, dttm_second)

    def test_import_urv_m2m(self):
        self.att_area2, _ = AttendanceArea.objects.update_or_create(
            code='2',
            external_system=self.ext_system,
            defaults={
                'name': 'Тестовая зона2',
            }
        )
        dttm_employee_coming = datetime.combine(date.today(), time(10, 48))
        dttm_employee_leaving = datetime.combine(date.today(), time(20, 13))
        dttm_employee2_coming = datetime.combine(date.today(), time(9, 34))
        dttm_employee2_leaving = datetime.combine(date.today(), time(21, 1))
        dttm_employee3_coming = datetime.combine(date.today(), time(8, 27))
        dttm_employee3_leaving = datetime.combine(date.today(), time(18, 19))
        TestRequestMock.responses["/transaction/listAttTransaction"] = {
            1: {
                "code": 0,
                "message": "success",
                "data": [
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc2",
                        "eventTime": dttm_employee2_coming.strftime('%Y-%m-%d %H:%M:%S'),
                        "pin": "2",
                        "name": "User",
                        "lastName": "User",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "accZone": "2",
                    },
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc3",
                        "eventTime": dttm_employee2_leaving.strftime('%Y-%m-%d %H:%M:%S'),
                        "pin": "2",
                        "name": "User",
                        "lastName": "User",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "accZone": "2",
                    },
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc4",
                        "eventTime": dttm_employee_coming.strftime('%Y-%m-%d %H:%M:%S'),
                        "pin": "1",
                        "name": "User",
                        "lastName": "User",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "accZone": "1",
                    },
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc5",
                        "eventTime": dttm_employee_leaving.strftime('%Y-%m-%d %H:%M:%S'),
                        "pin": "1",
                        "name": "User",
                        "lastName": "User",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "accZone": "1",
                    },
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc4",
                        "eventTime": dttm_employee3_coming.strftime('%Y-%m-%d %H:%M:%S'),
                        "pin": "3",
                        "name": "User",
                        "lastName": "User",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "accZone": "1",
                    },
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc5",
                        "eventTime": dttm_employee3_leaving.strftime('%Y-%m-%d %H:%M:%S'),
                        "pin": "3",
                        "name": "User",
                        "lastName": "User",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "accZone": "1",
                    },
                ],
            },
        }
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.root_shop,
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area2,
            shop=self.shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment1.employee.user_id,
            code='1',
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.employee.user_id,
            code='2',
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment3.employee.user_id,
            code='3',
        )
        WorkerDay.objects.create(
            shop_id=self.employment1.shop_id,
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(11)),
            dttm_work_end=datetime.combine(date.today(), time(20)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(9, 30)),
            dttm_work_end=datetime.combine(date.today(), time(21)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.root_shop.id,
            employee_id=self.employment3.employee_id,
            employment=self.employment3,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(8, 30)),
            dttm_work_end=datetime.combine(date.today(), time(18)),
            is_approved=True,
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), 6)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 3)
        self.assertEqual(AttendanceRecords.objects.count(), 6)
        employee_worker_day = WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today(), employee=self.employee1).first()
        employee2_worker_day = WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today(), employee=self.employee2).first()
        employee3_worker_day = WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=date.today(), employee=self.employee3).first()
        self.assertEqual(employee_worker_day.dttm_work_start, dttm_employee_coming)
        self.assertEqual(employee_worker_day.dttm_work_end, dttm_employee_leaving)
        self.assertEqual(employee2_worker_day.dttm_work_start, dttm_employee2_coming)
        self.assertEqual(employee2_worker_day.dttm_work_end, dttm_employee2_leaving)
        self.assertEqual(employee3_worker_day.dttm_work_start, dttm_employee3_coming)
        self.assertEqual(employee3_worker_day.dttm_work_end, dttm_employee3_leaving)

    def test_export_workers_m2m(self):
        self.att_area2, _ = AttendanceArea.objects.update_or_create(
            code='2',
            external_system=self.ext_system,
            defaults={
                'name': 'Тестовая зона2',
            }
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area2,
            shop=self.shop,
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            export_workers_zkteco()
        self.assertEqual(UserExternalCode.objects.count(), 5)

    def test_export_worker_on_employment_change(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        with patch.object(transaction, 'on_commit', lambda t: t()):
            with patch('src.integration.zkteco.requests', spec=TestRequestMock) as mock_request:
                mock_request.json.return_value = {"code": 0}
                mock_request.request.return_value = mock_request
                Employment.objects.create(
                    employee=self.employee1,
                    shop=self.shop,
                    position=self.position, 
                )
                self.assertEqual(
                    mock_request.request.call_args_list, 
                    [
                        call(
                            'POST', 
                            '/person/add', 
                            data=None, 
                            json={
                                'pin': settings.ZKTECO_USER_ID_SHIFT + self.user1.id, 
                                'deptCode': settings.ZKTECO_DEPARTMENT_CODE, 
                                'name': self.user1.first_name, 
                                'lastName': self.user1.last_name,
                            }, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                        call(
                            'POST', 
                            '/attAreaPerson/set', 
                            data=None, 
                            json={'pins': [settings.ZKTECO_USER_ID_SHIFT + self.user1.id], 'code': str(self.att_area.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        )
                    ]
                )
                self.assertTrue(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())

    def test_delete_worker_from_zkteco_on_employment_change(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.root_shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user=self.user1,
            code=settings.ZKTECO_USER_ID_SHIFT + self.user1.id,
        )   
        with patch.object(transaction, 'on_commit', lambda t: t()):
            with patch('src.integration.zkteco.requests', spec=TestRequestMock) as mock_request:
                mock_request.json.return_value = {"code": 0}
                mock_request.request.return_value = mock_request
                self.employment1.dt_fired = date(2019, 1, 1)
                self.employment1.save()
                self.assertEqual(
                    mock_request.request.call_args_list, 
                    [
                        call(
                            'POST', 
                            '/attAreaPerson/delete', 
                            data=None, 
                            json={'pins': [str(settings.ZKTECO_USER_ID_SHIFT + self.user1.id)], 'code': str(self.att_area.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                    ]
                )
                self.assertFalse(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())

    def test_delete_worker_from_zkteco_on_employment_change_user_code_not_deleted(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.root_shop,
        )
        Employment.objects.create(
            employee=self.employee1,
            shop=self.shop,
            position=self.position, 
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user=self.user1,
            code=settings.ZKTECO_USER_ID_SHIFT + self.user1.id,
        )   
        with patch.object(transaction, 'on_commit', lambda t: t()):
            with patch('src.integration.zkteco.requests', spec=TestRequestMock) as mock_request:
                mock_request.json.return_value = {"code": 0}
                mock_request.request.return_value = mock_request
                self.employment1.dt_fired = date(2019, 1, 1)
                self.employment1.save()
                self.assertEqual(
                    mock_request.request.call_args_list, 
                    [
                        call(
                            'POST', 
                            '/attAreaPerson/delete', 
                            data=None, 
                            json={'pins': [str(settings.ZKTECO_USER_ID_SHIFT + self.user1.id)], 'code': str(self.att_area.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                    ]
                )
                self.assertTrue(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())

    def test_delete_worker_from_zkteco_on_employment_delete(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.root_shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user=self.user1,
            code=settings.ZKTECO_USER_ID_SHIFT + self.user1.id,
        )   
        with patch.object(transaction, 'on_commit', lambda t: t()):
            with patch('src.integration.zkteco.requests', spec=TestRequestMock) as mock_request:
                mock_request.json.return_value = {"code": 0}
                mock_request.request.return_value = mock_request
                self.employment1.delete()
                self.assertEqual(
                    mock_request.request.call_args_list, 
                    [
                        call(
                            'POST', 
                            '/attAreaPerson/delete', 
                            data=None, 
                            json={'pins': [str(settings.ZKTECO_USER_ID_SHIFT + self.user1.id)], 'code': str(self.att_area.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                    ]
                )
                self.assertFalse(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())
    
    def test_change_zone_on_employment_change_shop(self):
        self.att_area2, _ = AttendanceArea.objects.update_or_create(
            code='2',
            external_system=self.ext_system,
            defaults={
                'name': 'Тестовая зона2',
            }
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        self.root_shop_code = ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.root_shop,
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user=self.user1,
            code=settings.ZKTECO_USER_ID_SHIFT + self.user1.id,
        )   
        with patch.object(transaction, 'on_commit', lambda t: t()):
            with patch('src.integration.zkteco.requests', spec=TestRequestMock) as mock_request:
                mock_request.json.return_value = {"code": 0}
                mock_request.request.return_value = mock_request
                
                self.employment1.shop = self.shop
                self.employment1.save()
                self.assertEqual(
                    mock_request.request.call_args_list, 
                    [
                        call(
                            'POST', 
                            '/attAreaPerson/set', 
                            data=None, 
                            json={'pins': [str(settings.ZKTECO_USER_ID_SHIFT + self.user1.id)], 'code': str(self.att_area.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                    ]
                )
                self.assertTrue(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())
                mock_request.request.call_args_list.clear()
                self.root_shop_code.attendance_area = self.att_area2
                self.root_shop_code.save()
                self.employment1.shop = self.root_shop
                self.employment1.save()
                self.assertEqual(
                    mock_request.request.call_args_list, 
                    [
                        call(
                            'POST', 
                            '/attAreaPerson/set', 
                            data=None, 
                            json={'pins': [str(settings.ZKTECO_USER_ID_SHIFT + self.user1.id)], 'code': str(self.att_area2.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                        call(
                            'POST', 
                            '/attAreaPerson/delete', 
                            data=None, 
                            json={'pins': [str(settings.ZKTECO_USER_ID_SHIFT + self.user1.id)], 'code': str(self.att_area.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                    ]
                )
                self.assertTrue(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())
    

    def test_not_delete_area_when_same_area_in_other_shop(self):
        self.maxDiff = None
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.root_shop,
        )
        with patch.object(transaction, 'on_commit', lambda t: t()):
            with patch('src.integration.zkteco.requests', spec=TestRequestMock) as mock_request:
                mock_request.json.return_value = {"code": 0}
                mock_request.request.return_value = mock_request
                Employment.objects.create(
                    shop=self.shop,
                    employee_id=self.employment1.employee_id,
                    position=self.position,
                )
                self.assertEqual(
                    mock_request.request.call_args_list, 
                    [
                        call(
                            'POST', 
                            '/person/add', 
                            data=None, 
                            json={
                                'pin': settings.ZKTECO_USER_ID_SHIFT + self.user1.id, 
                                'deptCode': settings.ZKTECO_DEPARTMENT_CODE, 
                                'name': self.user1.first_name, 
                                'lastName': self.user1.last_name,
                            }, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                        call(
                            'POST', 
                            '/attAreaPerson/set', 
                            data=None, 
                            json={'pins': [settings.ZKTECO_USER_ID_SHIFT + self.user1.id], 'code': str(self.att_area.code)}, 
                            params={'access_token': settings.ZKTECO_KEY}
                        ),
                    ]
                )
                mock_request.request.call_args_list.clear()
                self.employment1.dt_fired = date(2019, 1, 1)
                self.employment1.save()
                self.assertEqual(mock_request.request.call_args_list, [])
                self.assertTrue(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())


    def test_worker_not_exported_for_fired_person(self):
        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.root_shop,
        )
        self.employment1.dt_fired = date(2019, 1, 1)
        self.employment1.save()
        with patch.object(transaction, 'on_commit', lambda t: t()):
            with patch('src.integration.zkteco.requests', spec=TestRequestMock) as mock_request:
                mock_request.json.return_value = {"code": 0}
                mock_request.request.return_value = mock_request
                self.employment1.dt_hired = date(2018, 11, 1)
                self.employment1.save()
                self.assertEqual(mock_request.request.call_args_list, [])
                self.assertFalse(UserExternalCode.objects.filter(external_system=self.ext_system, user=self.user1).exists())

    def test_fact_not_duplicated_on_approve(self):
        dt = date.today()
        WorkerDay.objects.all().delete()
        AttendanceRecords.objects.all().delete()

        ShopExternalCode.objects.create(
            attendance_area=self.att_area,
            shop=self.shop,
        )

        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user=self.user2,
            code='1',
        )
        self.admin_group.has_perm_to_approve_other_shop_days = True
        self.admin_group.save()

        self.network.run_recalc_fact_from_att_records_on_plan_approve = True
        self.network.save()

        dttm = datetime.combine(dt, time(16, 1))

        TestRequestMock.responses["/transaction/listAttTransaction"] = {
            1:{
                "code": 0,
                "message": "success",
                "data": [
                    {
                        "id": "8a8080847322cd7f017323a7df9e0dc2",
                        "eventTime": dttm.strftime('%Y-%m-%d %H:%M:%S'),
                        "pin": "1",
                        "name": "User",
                        "lastName": "User",
                        "deptName": "Area Name",
                        "areaName": "Area Name",
                        "devSn": "CGXH201360029",
                        "verifyModeName": "15",
                        "accZone": "1",
                    },
                ],
            }
        }

        work_type_name = WorkTypeNameFactory()

        WorkTypeFactory(shop=self.shop, work_type_name=work_type_name)
        work_type = WorkTypeFactory(shop=self.shop2, work_type_name=work_type_name)

        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock):
            import_urv_zkteco()
        
        self.assertEqual(AttendanceRecords.objects.count(), 1)
        self.assertEqual(AttendanceRecords.objects.first().shop_id, self.shop.id)
        
        fact_wdays = WorkerDay.objects.filter(is_fact=True, employee=self.employee2, type_id=WorkerDay.TYPE_WORKDAY)
        plan_wdays = WorkerDay.objects.filter(is_fact=False, employee=self.employee2, type_id=WorkerDay.TYPE_WORKDAY)

        self.assertEqual(fact_wdays.count(), 2)

        fact_wdays.delete()

        self.assertEqual(fact_wdays.count(), 0)

        # не обязательно, но для полноты картины
        self.employment2.shop = self.shop2
        self.employment2.save()

        with patch.object(transaction, 'on_commit', lambda t: t()):

            wday_data = {
                'employee_id': self.employee2.id,
                'employment_id': self.employment2.id,
                'type': WorkerDay.TYPE_WORKDAY,
                'is_fact': True,
                'dttm_work_start': datetime.combine(dt, time(6)),
                'dttm_work_end': datetime.combine(dt, time(16)),
                'dt': dt,
                'shop_id': self.shop2.id,
                'worker_day_details': [
                    {
                        'work_type_id': work_type.id,
                        'work_part': 1.0, 
                    }
                ],
            }   

            response = self.client.post(
                self.get_url('WorkerDay-list'),
                self.dump_data(wday_data),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 201)

            wd_fact = response.json()

            wday_data['is_fact'] = False

            response = self.client.post(
                self.get_url('WorkerDay-list'),
                self.dump_data(wday_data),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 201)

            self.assertEqual(fact_wdays.count(), 1)
            self.assertEqual(plan_wdays.count(), 1)

            approve_data = {
                'dt_from': dt,
                'dt_to': dt,
                'shop_id': self.shop2.id,
                'is_fact': False,
            }
            response = self.client.post(
                self.get_url('WorkerDay-approve'),
                self.dump_data(approve_data),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)

            self.assertEqual(plan_wdays.count(), 2)
            self.assertEqual(fact_wdays.count(), 2)

            approve_data['is_fact'] = True
            response = self.client.post(
                self.get_url('WorkerDay-approve'),
                self.dump_data(approve_data),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200)

            self.assertEqual(plan_wdays.count(), 2)
            self.assertEqual(fact_wdays.count(), 2)
            self.assertTrue(fact_wdays.filter(is_approved=True, id=wd_fact['id']).exists())
            self.assertFalse(fact_wdays.filter(Q(dttm_work_start__isnull=True) | Q(dttm_work_end__isnull=True)).exists())
