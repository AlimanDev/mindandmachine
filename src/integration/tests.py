from datetime import datetime, time, date, timedelta

from django.test import override_settings

from django.utils.timezone import now
from rest_framework.test import APITestCase
from unittest.mock import patch

from src.timetable.models import WorkerDay, AttendanceRecords
from src.base.models import WorkerPosition, Employment
from src.integration.models import AttendanceArea, ExternalSystem, UserExternalCode, ShopExternalCode
from src.integration.tasks import import_urv_zkteco, export_workers_zkteco, delete_workers_zkteco
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


@override_settings(ZKTECO_HOST='')
class TestIntegration(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.dt = now().date()

        create_departments_and_users(self)
        self.ext_system, _ = ExternalSystem.objects.get_or_create(
            code='zkteco',
            defaults={
                'name':'ZKTeco',
            },
        )
        self.position = WorkerPosition.objects.create(
            name='Должность',
            network=self.network,
        )
        self.att_area, _ = AttendanceArea.objects.update_or_create(
            code='1',
            external_system=self.ext_system,
            defaults={
                'name': 'Тестовая зона',
            }
        )

        Employment.objects.filter(
            shop=self.shop,
        ).update(
            position=self.position,
        )
        
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
            type=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(11)),
            dttm_work_end=datetime.combine(date.today(), time(20)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.employment2.shop_id,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            type=WorkerDay.TYPE_WORKDAY,
            dt=date.today(),
            dttm_work_start=datetime.combine(date.today(), time(9, 30)),
            dttm_work_end=datetime.combine(date.today(), time(21)),
            is_approved=True,
        )
        WorkerDay.objects.create(
            shop_id=self.root_shop.id,
            employee_id=self.employment3.employee_id,
            employment=self.employment3,
            type=WorkerDay.TYPE_WORKDAY,
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
