import json
from datetime import datetime, time, date, timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction

from django.test import override_settings

from django.utils.timezone import now
from rest_framework.test import APITestCase
from unittest.mock import patch
import requests

from src.timetable.models import WorkerDay, AttendanceRecords
from src.base.models import WorkerPosition, Employment
from src.integration.models import ExternalSystem, UserExternalCode, ShopExternalCode
from src.integration.tasks import import_urv_zkteco, export_workers_zkteco, delete_workers_zkteco
from src.util.test import create_departments_and_users

dttm_first = (datetime.now() - timedelta(hours=2)).replace(microsecond=0)
dttm_second = datetime.now().replace(microsecond=0)
dttm_third = (datetime.now() + timedelta(hours=2)).replace(microsecond=0)

class TestRequestMock:
    responses = {
        "/transaction/listAttTransaction": {
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
        },
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
        self.ext_system = ExternalSystem.objects.create(
            name='ZKTeco',
            code='zkteco',
        )
        self.position = WorkerPosition.objects.create(
            name='Должность',
            network=self.network,
        )

        Employment.objects.filter(
            shop=self.shop,
        ).update(
            position=self.position,
        )
        
        self.client.force_authenticate(user=self.user1)


    def test_export_workers(self):
        ShopExternalCode.objects.create(
            external_system=self.ext_system,
            shop=self.shop,
            code='1',
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            export_workers_zkteco()
        self.assertEqual(UserExternalCode.objects.count(), 5)

    
    def test_delete_workers(self):
        ShopExternalCode.objects.create(
            external_system=self.ext_system,
            shop=self.shop,
            code='1',
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            export_workers_zkteco()
            self.employment2.dt_fired = date.today() - timedelta(days=2)
            self.employment2.save()
            delete_workers_zkteco()
        self.assertEqual(UserExternalCode.objects.count(), 4)
    
    def test_import_urv(self):
        ShopExternalCode.objects.create(
            external_system=self.ext_system,
            shop=self.shop,
            code='1',
        )
        UserExternalCode.objects.create(
            external_system=self.ext_system,
            user_id=self.employment2.user_id,
            code='1',
        )
        with patch('src.integration.zkteco.requests', new_callable=TestRequestMock) as mock_request:
            import_urv_zkteco()

        self.assertEqual(WorkerDay.objects.count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.count(), 2)
        self.assertEqual(AttendanceRecords.objects.filter(type=AttendanceRecords.TYPE_LEAVING).count(), 1)
        self.assertEqual(AttendanceRecords.objects.filter(type=AttendanceRecords.TYPE_COMING).first().dttm, dttm_first)
        self.assertEqual(AttendanceRecords.objects.filter(type=AttendanceRecords.TYPE_LEAVING).first().dttm, dttm_third)
