import datetime
from datetime import date

from django.conf import settings
from django.utils import timezone

from src.db.models import User
from src.util.test import LocalTestCase


class TestCashier(LocalTestCase):
    def test_change_password(self):
        self.auth()

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'old_password': 'qqq',
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        # {'error_type': 'AccessForbidden', 'error_message': ''}
        # self.assertEqual(response.json['code'], 400)
        # self.assertEqual(response.json['data']['error_type'], 'AuthError')

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 5,
            'old_password': self.USER_PASSWORD,
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        # {'error_type': 'DoesNotExist', 'error_message': 'error in api_method'}
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_type'], 'AccessForbidden')
        # self.assertEqual(response.json['data']['error_message'], 'You are not allowed to edit this user')

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'old_password': self.USER_PASSWORD,
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'old_password': 'new_password',
            'new_password': self.USER_PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        self.user1.save()
        self.auth()

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'old_password': self.USER_PASSWORD,
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

    def test_change_cashier_info(self):
        self.auth()
        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 1,
            'first_name': 'Benedick',
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json['code'], 200)
        # self.assertEqual(response.json['data']['new_first_name'], 'Benedick')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 5,
            'first_name': 'Boss',
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_message'], 'You are not allowed to edit this user')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 2,
            'first_name': 'Viktor',
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json['code'], 200)
        # self.assertEqual(response.json['data']['new_first_name'], 'Viktor')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 1,
            'first_name': 'Viktor',
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json['code'], 403)
        # self.assertEqual(response.json['data']['error_message'], 'You are not allowed to edit this group')

        response = self.api_post('/api/timetable/cashier/change_cashier_info', {
            'user_id': 1,
            'first_name': 'Viktor',
            'middle_name': 'middle_name',
            'last_name': 'last_name',
            'birthday': date(1990, 2, 3),
        })
        self.assertEqual(response.status_code, 200)
        # 'error_message': "[('password', ['This field is required.'])]"
        # self.assertEqual(response.json['code'], 200)
        # self.assertEqual(response.json['data']['new_first_name'], 'Viktor')
        # self.assertEqual(response.json['data']['new_middle_name'], 'middle_name')
        # self.assertEqual(response.json['data']['new_last_name'], 'last_name')
        # self.assertEqual(response.json['data']['new_birthday'], '1990-02-03')


class TestGetCashierList(LocalTestCase):
    """Tests for timetable/cashier/get_cashiers_list"""
    get_cashiers_list_url = '/api/timetable/cashier/get_cashiers_list'

    def setUp(self, periodclients=True):
        super().setUp(periodclients)
        self.auth()

        self.staff1: User = User.objects.create_user(
            'staff1',
            'staff1@test.ru',
            '4242',
            shop=self.root_shop,
            function_group=self.employee_group,
            attachment_group=User.GROUP_STAFF,
            last_name='Дурак7',
            first_name='Иван7',
            id=99,
            dt_hired=timezone.now() - datetime.timedelta(days=5),
            dt_fired=timezone.now() + datetime.timedelta(days=3),
        )

    def test_filter_defaults(self):
        # staff1 meets both defaults
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 2)

        self.staff1.dt_hired = timezone.now() + datetime.timedelta(days=11)
        self.staff1.save()

        # staff1 hired after default dt_hired_before
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)

        self.staff1.dt_hired = timezone.now() - datetime.timedelta(days=5)
        self.staff1.dt_fired = timezone.now() - datetime.timedelta(days=1)
        self.staff1.save()

        # staff1 fired before default dt_fired_after
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)

        # show_all = true
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
            'show_all': True,
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 2)

    def test_dt_hired_before(self):
        # staff1 included - hired before dt_hired_before filter
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
            'dt_hired_before': (timezone.now() - datetime.timedelta(days=3)).date().strftime(settings.QOS_DATE_FORMAT),
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 2)

        # staff1 excluded - hired after dt_hired_before filter
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
            'dt_hired_before': (timezone.now() - datetime.timedelta(days=8)).date().strftime(settings.QOS_DATE_FORMAT),
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)

    def test_dt_fired_after(self):
        # staff1 included - fired after dt_fired_after value
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
            'dt_fired_after': (timezone.now() + datetime.timedelta(days=1)).date().strftime(settings.QOS_DATE_FORMAT),
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 2)

        # staff1 excluded - fired before dt_fired_after value
        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
            'dt_fired_after': (timezone.now() + datetime.timedelta(days=5)).date().strftime(settings.QOS_DATE_FORMAT),
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 1)

    def test_consider_outsource(self):
        User.objects.create_user(
            'outscore1',
            'outscoer1@test.ru',
            '4242',
            shop=self.root_shop,
            function_group=self.employee_group,
            attachment_group=User.GROUP_OUTSOURCE,
            last_name='Дурак7',
            first_name='Иван7',
            id=98,
            dt_hired=timezone.now() - datetime.timedelta(days=5),
            dt_fired=timezone.now() + datetime.timedelta(days=3),
        )

        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 2)

        response = self.api_get(self.get_cashiers_list_url, {
            'shop_id': 1,
            'consider_outsource': True,
        })
        self.assertResponseCodeEqual(response, 200)
        self.assertResponseDataListCount(response, 3)
