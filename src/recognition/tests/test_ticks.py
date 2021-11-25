from django.test import override_settings
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from src.recognition.models import Tick, TickPoint
from src.util.mixins.tests import TestsHelperMixin
from src.timetable.models import WorkerDay, AttendanceRecords
from datetime import date, timedelta, datetime, time


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

    def _authorize_tick_point(self):
        t = TickPoint.objects.create(
            network=self.network,
            name='test',
            shop=self.shop,
        )

        response = self.client.post(
            path='/api/v1/token-auth/',
            data={
                'key': t.key,
            }
        )

        token = response.json()['token']
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Token %s' % token
        return response

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
