from django.utils.timezone import now

from src.db.models import User
from src.util.test import LocalTestCase


class AuthTestCase(LocalTestCase):
    def test_auth_cycle_success(self):
        response = self.api_get('/api/auth/is_signed')
        self.assertEqual(response.json()['data']['is_signed'], False)

        response = self.api_post(
            '/api/auth/signin',
            {
                'username': LocalTestCase.USER_USERNAME,
                'password': LocalTestCase.USER_PASSWORD,
            }
        )
        self.assertEqual(response.json()['data']['id'], 1)

        response = self.api_get('/api/auth/is_signed')
        self.assertEqual(response.json()['data']['is_signed'], True)
        self.assertEqual(response.json()['data']['user']['id'], 1)

        response = self.api_post('/api/auth/signout')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        response = self.api_get('/api/auth/is_signed')
        self.assertEqual(response.json()['data']['is_signed'], False)

        user = User.objects.get(pk=1)
        user.dt_fired = now().date()
        user.save()

        response = self.api_post(
            '/api/auth/signin',
            {
                'username': LocalTestCase.USER_USERNAME,
                'password': LocalTestCase.USER_PASSWORD,
            }
        )
        self.assertEqual(response.json()['data']['error_type'], 'NotActiveError')
