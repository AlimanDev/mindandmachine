from src.db.models import User
from src.util.test import TestCase


class AuthTestCase(TestCase):
    def set_up(self):
        User.objects.create_user('user123', 'q@q.com', 'qq12', id=23)

    def test_auth_cycle_success(self):
        data = self.do_get('/auth/is_signed')
        self.assertEqual(data['is_signed'], False)

        data = self.do_post('/auth/signin', {'username': 'user123', 'password': 'qq12'})
        self.assertEqual(data['id'], 23)

        data = self.do_get('/auth/is_signed')
        self.assertEqual(data['is_signed'], True)
        self.assertEqual(data['user']['id'], 23)

        self.do_post('/auth/signout')

        data = self.do_get('/auth/is_signed')
        self.assertEqual(data['is_signed'], False)
