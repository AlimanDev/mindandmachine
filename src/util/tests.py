from src.util.test import LocalTestCase

class TestApiMethod(LocalTestCase):

    def setUp(self):
        super().setUp()

    def auth(self, username):
        self.client.post(
            '/api/auth/signin',
            {
                'username': username,
                'password': self.USER_PASSWORD
            }
        )


    def test_access_admin_group(self):
        # user1 = admin_group
        self.auth(self.USER_USERNAME)

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)


    def test_access_hq_group(self):
        # user5 = hq_group
        self.auth('user5')

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)


    def test_access_chief_group(self):
        # user6 = chief_group
        self.auth('user6')

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)


    def test_access_employee_group(self):
        # user7 = employee_group
        self.auth('user7')

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 403)
        self.assertEqual(response.json['data']['error_message'],
                         'Вы не можете просматрировать информацию о других пользователях')


    def test_auth_required(self):
        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 401)
        self.assertEqual(response.json['data']['error_type'], 'AuthRequired')


    def test_valid_form(self):
        self.auth(self.USER_USERNAME)

        response = self.api_get('/api/timetable/auto_settings/get_status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 400)
        self.assertEqual(response.json['data']['error_message'], "[('dt', ['This field is required.'])]")




