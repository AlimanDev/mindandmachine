from src.util.test import LocalTestCase
from src.db.models import User
from datetime import date


class TestCashier(LocalTestCase):

    # def setUp(self):
    #     super().setUp()

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
        self.assertEqual(response.json['code'], 200)

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'old_password': 'new_password',
            'new_password': self.USER_PASSWORD,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

        self.user1.save()
        self.auth()

        response = self.api_post('/api/timetable/cashier/password_edit', {
            'user_id': 1,
            'old_password': self.USER_PASSWORD,
            'new_password': 'new_password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

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
