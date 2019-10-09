from src.util.test import LocalTestCase


class TestApiMethod(LocalTestCase):
    def auth(self, username):
        self.client.post(
            '/api/auth/signin',
            {
                'username': username,
                'password': self.USER_PASSWORD
            }
        )

    def test_access_root_level_group(self):
        # user1 = admin_group - root shop
        self.auth(self.USER_USERNAME)

        response = self.api_get(
            '/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get(
            '/api/shop/get_department?shop_id={}'.format(self.root_shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

    def test_access_1_level_group(self):
        # user5 = reg shop chief_group -only region 1
        self.auth('user5')

        response = self.api_get(
            '/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get(
            '/api/shop/get_department?shop_id={}'.format(self.shop2.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get(
            '/api/shop/get_department?shop_id={}'.format(self.shop3.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 403)

    def test_access_2_level_shop_group(self):
        # user6 = shop chief_group only own shop
        self.auth('user6')

        response = self.api_get(
            '/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get('/api/shop/get_department?shop_id={}'.format(self.root_shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 403)

        response = self.api_get('/api/shop/get_department?shop_id={}'.format(self.shop3.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 403)

    def test_access_parent_level_shop_group(self):
        # user4 = shop admin_group - 1 level up
        self.auth('user4')

        response = self.api_get(
            '/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get('/api/shop/get_department?shop_id={}'.format(self.reg_shop1.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get('/api/shop/get_department?shop_id={}'.format(self.shop2.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get('/api/shop/get_department?shop_id={}'.format(self.shop3.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 403)

    def test_access_employee_group(self):
        # user7 = employee_group
        self.auth('user7')

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 200)

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(self.shop2.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 403)
        self.assertEqual(response.json()['data']['error_message'],
                         'Вы не можете просматрировать информацию по другим магазинам')

    def test_auth_required(self):
        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(self.shop.id))
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 401)
        self.assertEqual(response.json()['data']['error_type'], 'AuthRequired')

    def test_valid_form(self):
        self.auth(self.USER_USERNAME)

        response = self.api_get('/api/timetable/auto_settings/get_status')
        self.assertEqual(response.status_code, 200)
        self.assertResponseCodeEqual(response, 400)
        self.assertEqual(response.json()['data']['error_message'], "[('dt', ['This field is required.'])]")
