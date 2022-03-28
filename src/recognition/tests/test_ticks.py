from datetime import date, timedelta, datetime, time
from unittest import mock

from django.test import override_settings
from freezegun import freeze_time
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from src.recognition.models import ShopIpAddress, Tick, TickPoint
from src.timetable.models import WorkerDay, AttendanceRecords
from src.util.mixins.tests import TestsHelperMixin


class TestTicksViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        WorkerDay.objects.create(
            dt=date.today(),
            type_id=WorkerDay.TYPE_WORKDAY,
            employee=cls.employee2,
            employment=cls.employment2,
            shop=cls.shop2,
            is_approved=True,
            is_vacancy=True,
            dttm_work_start=datetime.combine(date.today(), time(10)),
            dttm_work_end=datetime.combine(date.today(), time(20)),
        )
        cls.network.trust_tick_request = True
        cls.network.save()

    def setUp(self):
        self._set_authorization_token(self.user2.username)

    def test_create_and_update_and_list_ticks(self):
        resp_coming = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': self.shop2.code, 'employee_id': self.employee2.id}),
            content_type='application/json',
        )
        self.assertEqual(resp_coming.status_code, status.HTTP_200_OK)

        resp_leaving = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_LEAVING, 'shop_code': self.shop2.code, 'employee_id': self.employee2.id}),
            content_type='application/json',
        )
        self.assertEqual(resp_leaving.status_code, status.HTTP_200_OK)

        self.assertEqual(Tick.objects.count(), 2)

        resp_list = self.client.get(self.get_url('Tick-list'))
        self.assertEqual(resp_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_list.json()), 2)

    def _test_geo(self, allowed_distance, shop_lat, shop_lon, user_lat, user_lon):
        self.shop2.latitude = shop_lat
        self.shop2.longitude = shop_lon
        self.shop2.save()
        self.network.allowed_geo_distance_km = allowed_distance
        self.network.save()
        resp = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({
                'type': Tick.TYPE_COMING,
                'shop_code': self.shop2.code,
                'lat': user_lat,
                'lon': user_lon,
                'employee_id': self.employee2.id,
            }),
            content_type='application/json',
        )
        return resp

    def test_geoposition_check_failed(self):
        resp = self._test_geo(10, 52.2296756, 21.0122287, 52.406374, 16.925168)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.json()['non_field_errors'][0],
            "Дистанция до магазина не должна превышать 10.00 км (сейчас 279.35 км)",
        )

    def test_geoposition_check_passed(self):
        resp = self._test_geo(10, 52.2296756, 21.0122287, 52.306374, 21.0122287)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_create_without_employment_fired(self):
        self.employment2.dt_fired = date(2020, 2, 1)
        self.employment2.save()
        with override_settings(USERS_WITH_ACTIVE_EMPLOYEE_OR_VACANCY_ONLY=True):
            resp_coming = self.client.post(
                self.get_url('Tick-list'),
                data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': self.shop.code, 'employee_id': self.employee2.id}),
                content_type='application/json',
            )
        self.assertEqual(resp_coming.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp_coming.json(), 
            {
                "error": "У вас нет трудоустройства на текущий момент, "\
                "действие выполнить невозможно, пожалуйста, обратитесь к вашему руководству"
            },
        )

    def test_create_without_employment_hired(self):
        self.employment2.dt_fired = None
        self.employment2.dt_hired = date.today() + timedelta(1)
        self.employment2.save()
        with freeze_time(datetime.now() - timedelta(hours=self.shop.get_tz_offset())):
            with override_settings(USERS_WITH_ACTIVE_EMPLOYEE_OR_VACANCY_ONLY=True):
                resp_coming = self.client.post(
                    self.get_url('Tick-list'),
                    data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': self.shop.code, 'employee_id': self.employee2.id}),
                    content_type='application/json',
                )
        self.assertEqual(resp_coming.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp_coming.json(), 
            {
                "error": "У вас нет трудоустройства на текущий момент, "\
                "действие выполнить невозможно, пожалуйста, обратитесь к вашему руководству"
            },
        )


    def test_create_and_update_tick_no_type(self):
        resp_no_type = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_NO_TYPE, 'shop_code': self.shop.code, 'employee_id': self.employee2.id}),
            content_type='application/json',
        )

        no_type_data = resp_no_type.json()

        self.assertEqual(no_type_data['type'], Tick.TYPE_NO_TYPE)
        self.assertEqual(no_type_data['user_id'], self.user2.id)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 0)
        self.assertEqual(AttendanceRecords.objects.get(dttm=no_type_data['dttm']).type, AttendanceRecords.TYPE_NO_TYPE)

        resp_comming = self.client.put(
            self.get_url('Tick-detail', pk=resp_no_type.json()['id']),
            data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': self.shop2.code, 'employee_id': self.employee2.id}),
            content_type='application/json',
        )

        comming_data = resp_comming.json()

        self.assertEqual(comming_data['type'], Tick.TYPE_COMING)
        self.assertEqual(comming_data['user_id'], self.user2.id)
        self.assertEqual(comming_data['dttm'], no_type_data['dttm'])
        self.assertEqual(comming_data['tick_point_id'], no_type_data['tick_point_id'])
        self.assertEqual(Tick.objects.get(user_id=comming_data['user_id'], dttm=comming_data['dttm']).type, Tick.TYPE_COMING)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.get(dttm=no_type_data['dttm']).type, AttendanceRecords.TYPE_COMING)

        resp_leaving = self.client.put(
            self.get_url('Tick-detail', pk=resp_no_type.json()['id']),
            data=self.dump_data({'type': Tick.TYPE_LEAVING, 'shop_code': self.shop2.code, 'employee_id': self.employee2.id}),
            content_type='application/json',
        )

        leaving_data = resp_leaving.json()
  
        self.assertEqual(leaving_data['type'], Tick.TYPE_COMING)
        self.assertEqual(leaving_data['dttm'], no_type_data['dttm'])
        self.assertEqual(Tick.objects.get(user_id=comming_data['user_id'], dttm=comming_data['dttm']).type, Tick.TYPE_COMING)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(AttendanceRecords.objects.get(dttm=no_type_data['dttm']).type, AttendanceRecords.TYPE_COMING)
        self.assertEqual(AttendanceRecords.objects.all().count(), 1)

    def test_cant_create_att_record_withot_active_empl(self):
        self.employment2.dt_fired = date.today() - timedelta(days=2)
        self.employment2.save()

        with self.assertRaisesMessage(ValidationError, 'У вас нет активного трудоустройства'):
            AttendanceRecords.objects.create(
                user_id=self.employee2.user_id,
                shop=self.shop,
                dttm=datetime.now(),
            )

    def test_get_ticks_for_tick_point(self):
        tick_point_id = self._authorize_tick_point().json()['tick_point']['id']
        dt = date.today()
        self.shop.timezone = 'UTC'
        self.shop.save()
        Tick.objects.create(
            user=self.user1,
            dttm=datetime.combine(dt - timedelta(1), time(16, 0, 2)),
            employee=self.employee1,
            tick_point_id=tick_point_id,
            type=Tick.TYPE_COMING,
            lateness=timedelta(0),
        )
        Tick.objects.create(
            user=self.user1,
            dttm=datetime.combine(dt, time(2, 3, 43)),
            employee=self.employee1,
            tick_point_id=tick_point_id,
            type=Tick.TYPE_LEAVING,
            lateness=timedelta(0),
        )
        response = self.client.get(self.get_url('Tick-list'))
        self.assertEqual(len(response.json()), 2)
        Tick.objects.create(
            user=self.user1,
            dttm=datetime.combine(dt, time(16, 0, 2)),
            employee=self.employee1,
            tick_point_id=tick_point_id,
            type=Tick.TYPE_COMING,
            lateness=timedelta(0),
        )
        response = self.client.get(self.get_url('Tick-list'))
        self.assertEqual(len(response.json()), 2)
        tick_point_id2 = self._authorize_tick_point().json()['tick_point']['id']
        response = self.client.get(self.get_url('Tick-list'))
        self.assertEqual(len(response.json()), 2)
        self.assertNotEqual(response.json()[0]['tick_point_id'], tick_point_id2)

    def test_get_ticks_with_yesterday_leving_for_tick_point(self):
        tick_point_id = self._authorize_tick_point().json()['tick_point']['id']
        dt = date.today()
        self.shop.timezone = 'UTC'
        self.shop.save()
        Tick.objects.create(
            user=self.user1,
            dttm=datetime.combine(dt - timedelta(1), time(8, 0, 2)),
            employee=self.employee1,
            tick_point_id=tick_point_id,
            type=Tick.TYPE_COMING,
            lateness=timedelta(0),
        )
        Tick.objects.create(
            user=self.user1,
            dttm=datetime.combine(dt - timedelta(1), time(20, 3, 43)),
            employee=self.employee1,
            tick_point_id=tick_point_id,
            type=Tick.TYPE_LEAVING,
            lateness=timedelta(0),
        )
        response = self.client.get(self.get_url('Tick-list'))
        self.assertEqual(len(response.json()), 0)

    def _test_lateness(self, type, dttm, assert_lateness, tick_id=None):
        with mock.patch('src.recognition.views.now', lambda: dttm - timedelta(hours=3)):
            data = {'employee_id': self.employee2.id, 'type': type, 'shop_code': self.shop2.code }
            if not tick_id:
                response = self.client.post(self.get_url('Tick-list'), data)
            else:
                response = self.client.put(self.get_url('Tick-detail', pk=tick_id), data)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(assert_lateness, response.json()['lateness'])
            return response.json()['id']

    def test_lateness(self):
        comming_time = datetime.combine(date.today(), time(9))
        leaving_time = datetime.combine(date.today(), time(21))
        tick_id = self._test_lateness(Tick.TYPE_NO_TYPE, comming_time, None) # пришел раньше, но пока нет типа
        self._test_lateness(Tick.TYPE_COMING, comming_time, -3600, tick_id=tick_id) # есть тип, обновляем
        tick_id = self._test_lateness(Tick.TYPE_NO_TYPE, leaving_time, None) # ушел позже, но пока нет типа
        self._test_lateness(Tick.TYPE_LEAVING, leaving_time, -3600, tick_id=tick_id) # есть тип, обновляем
        Tick.objects.all().delete()
        WorkerDay.objects.filter(is_fact=True).delete()
        comming_time = datetime.combine(date.today(), time(11))
        leaving_time = datetime.combine(date.today(), time(19))
        self._test_lateness(
            Tick.TYPE_COMING, 
            comming_time, 
            3600, 
            tick_id=self._test_lateness(Tick.TYPE_NO_TYPE, comming_time, None),
        ) # опоздал
        self._test_lateness(
            Tick.TYPE_LEAVING, 
            leaving_time, 
            3600, 
            tick_id=self._test_lateness(Tick.TYPE_NO_TYPE, leaving_time, None),
        ) # ушел раньше
        Tick.objects.all().delete()
        WorkerDay.objects.filter(is_fact=True).delete()
        comming_time = datetime.combine(date.today() + timedelta(1), time(9))
        leaving_time = datetime.combine(date.today() + timedelta(1), time(21))
        self._test_lateness(
            Tick.TYPE_COMING, 
            comming_time, 
            None,
            tick_id=self._test_lateness(Tick.TYPE_NO_TYPE, comming_time, None),
        ) # нет плана
        self._test_lateness(
            Tick.TYPE_LEAVING, 
            leaving_time, 
            None,
            tick_id=self._test_lateness(Tick.TYPE_NO_TYPE, leaving_time, None),
        ) # нет плана
        Tick.objects.all().delete()
        WorkerDay.objects.filter(is_fact=True).delete()
        self.network.trust_tick_request = False
        self.network.save()
        comming_time = datetime.combine(date.today(), time(9))
        leaving_time = datetime.combine(date.today(), time(21))
        self._test_lateness(
            Tick.TYPE_COMING, 
            comming_time, 
            None, 
            tick_id=self._test_lateness(Tick.TYPE_NO_TYPE, comming_time, None),
        ) # нельзя отметиться без фото
        self._test_lateness(
            Tick.TYPE_LEAVING, 
            leaving_time, 
            None, 
            tick_id=self._test_lateness(Tick.TYPE_NO_TYPE, leaving_time, None),
        ) # нельзя отметиться без фото

    def test_ip_auth(self):
        self._authorize_tick_point()
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
            HTTP_X_FORWARDED_FOR='123.123.123.123',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.defaults.pop('HTTP_AUTHORIZATION', None)
        TickPoint.objects.all().delete()
        ip_auth = ShopIpAddress.objects.create(
            shop=self.shop,
            ip_address='123.123.123.123',
        )
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
            HTTP_X_FORWARDED_FOR='123.123.123.123',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp_coming = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_COMING, 'user_id': self.user2.id, 'employee_id': self.employee2.id}),
            content_type='application/json',
            HTTP_X_FORWARDED_FOR='123.123.123.123',
        )
        self.assertEqual(resp_coming.status_code, status.HTTP_200_OK)
        self.assertTrue(TickPoint.objects.filter(name=f'autocreate tickpoint {self.shop.id}').exists())
        tick_point = TickPoint.objects.create(name='Test', shop=self.shop, network=self.network)
        ip_auth.tick_point = tick_point
        ip_auth.save()
        resp_leaving = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_LEAVING, 'user_id': self.user2.id, 'employee_id': self.employee2.id}),
            content_type='application/json',
            HTTP_X_FORWARDED_FOR='123.123.123.123',
        )
        self.assertEqual(resp_leaving.status_code, status.HTTP_200_OK)
        self.assertNotEqual(Tick.objects.first().tick_point_id, Tick.objects.last().tick_point_id)
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
            HTTP_X_FORWARDED_FOR='123.123.123.12',
        )
        self.assertEqual(resp.status_code, 403)
