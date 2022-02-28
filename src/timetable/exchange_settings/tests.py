from rest_framework import status
from rest_framework.test import APITestCase
from src.util.mixins.tests import TestsHelperMixin

from src.util.test import create_departments_and_users

from src.timetable.models import ExchangeSettings


class TestExchangeSettings(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/exchange_settings/'
        cls.create_departments_and_users()
        cls.exchange_serttings1 = ExchangeSettings.objects.create(network=cls.network)
        cls.exchange_serttings2 = ExchangeSettings.objects.create(network=cls.network)

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}')
        self.assertEqual(len(response.json()), 2)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.exchange_serttings1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.exchange_serttings1.id, 
            'constraints': '{"second_day_before": 40, "second_day_after": 32, "first_day_after": 32, "first_day_before": 40, "1day_before": 40, "1day_after": 40}', 
            'automatic_create_vacancies': False, 
            'automatic_delete_vacancies': False, 
            'automatic_check_lack_timegap': '7 00:00:00', 
            'automatic_holiday_worker_select_timegap': '8 00:00:00', 
            'automatic_exchange': False,
            'max_working_hours': 192, 
            'automatic_create_vacancy_lack_min': 0.5, 
            'automatic_delete_vacancy_lack_max': 0.3, 
            'automatic_worker_select_timegap': '1 00:00:00', 
            'automatic_worker_select_timegap_to': '2 00:00:00', 
            'automatic_worker_select_overflow_min': 0.8, 
            'working_shift_min_hours': '04:00:00', 
            'working_shift_max_hours': '12:00:00', 
            'automatic_worker_select_tree_level': 1, 
            'network': self.network.id, 
            'exclude_positions': [],
            'outsources': [],
        }
        resp = response.json()
        resp.pop('dttm_modified')
        self.assertEqual(resp, data)

    
    def test_create(self):
        data = {
            'max_working_hours': 200,
            'automatic_create_vacancy_lack_min': 0.8, 
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = {
            'id': response.json()['id'], 
            'constraints': '{"second_day_before": 40, "second_day_after": 32, "first_day_after": 32, "first_day_before": 40, "1day_before": 40, "1day_after": 40}', 
            'automatic_create_vacancies': False, 
            'automatic_delete_vacancies': False, 
            'automatic_check_lack_timegap': '7 00:00:00', 
            'automatic_holiday_worker_select_timegap': '8 00:00:00', 
            'automatic_exchange': False,
            'max_working_hours': 200, 
            'automatic_create_vacancy_lack_min': 0.8, 
            'automatic_delete_vacancy_lack_max': 0.3, 
            'automatic_worker_select_timegap': '1 00:00:00', 
            'automatic_worker_select_timegap_to': '2 00:00:00', 
            'automatic_worker_select_overflow_min': 0.8, 
            'working_shift_min_hours': '04:00:00', 
            'working_shift_max_hours': '12:00:00', 
            'automatic_worker_select_tree_level': 1, 
            'network': None, 
            'exclude_positions': [],
            'outsources': [],
        }
        resp = response.json()
        resp.pop('dttm_modified')
        self.assertEqual(resp, data)


    def test_update(self):
        data = {
            'max_working_hours': 200,
            'automatic_create_vacancy_lack_min': 0.8, 
        }
        response = self.client.put(f'{self.url}{self.exchange_serttings1.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.exchange_serttings1.id, 
            'constraints': '{"second_day_before": 40, "second_day_after": 32, "first_day_after": 32, "first_day_before": 40, "1day_before": 40, "1day_after": 40}', 
            'automatic_create_vacancies': False, 
            'automatic_delete_vacancies': False, 
            'automatic_check_lack_timegap': '7 00:00:00', 
            'automatic_holiday_worker_select_timegap': '8 00:00:00', 
            'automatic_exchange': False,
            'max_working_hours': 200, 
            'automatic_create_vacancy_lack_min': 0.8, 
            'automatic_delete_vacancy_lack_max': 0.3, 
            'automatic_worker_select_timegap': '1 00:00:00', 
            'automatic_worker_select_timegap_to': '2 00:00:00', 
            'automatic_worker_select_overflow_min': 0.8, 
            'working_shift_min_hours': '04:00:00', 
            'working_shift_max_hours': '12:00:00', 
            'automatic_worker_select_tree_level': 1, 
            'network': self.network.id, 
            'exclude_positions': [],
            'outsources': [],
        }
        resp = response.json()
        resp.pop('dttm_modified')
        self.assertEqual(resp, data)


    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.exchange_serttings1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
