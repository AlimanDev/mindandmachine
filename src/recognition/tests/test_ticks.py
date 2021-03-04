from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from src.recognition.models import Tick
from src.util.mixins.tests import TestsHelperMixin
from src.timetable.models import WorkerDay
from datetime import date


@override_settings(TRUST_TICK_REQUEST=True)
class TestTicksViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        WorkerDay.objects.create(
            dt=date.today(),
            type=WorkerDay.TYPE_WORKDAY,
            worker=cls.user2,
            employment=cls.employment2,
            shop=cls.shop2,
            is_approved=True,
            is_vacancy=True,
        )

    def setUp(self):
        self._set_authorization_token(self.user2.username)

    def test_create_and_update_and_list_ticks(self):
        resp_coming = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': self.shop2.code}),
            content_type='application/json',
        )
        self.assertEqual(resp_coming.status_code, status.HTTP_200_OK)

        resp_leaving = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_LEAVING, 'shop_code': self.shop2.code}),
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

    def test_create_without_employment(self):
        self.employment2.dt_fired = date(2020, 2, 1)
        self.employment2.save()
        with override_settings(USERS_WITH_ACTIVE_EMPLOYEE_OR_VACANCY_ONLY=True):
            resp_coming = self.client.post(
                self.get_url('Tick-list'),
                data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': self.shop.code}),
                content_type='application/json',
            )
        self.assertEqual(resp_coming.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp_coming.json(), {"error": "Действие невозможно, обратитесь к вашему руководителю"})
