from unittest.mock import Mock

from django.test import TestCase
from django.db import connection
from django.conf import settings

from src.apps.base.models import Shop
from src.common.mixins.tests import TestsHelperMixin
from src.common.decorators import cached_method, require_lock


class TestDecorators(TestsHelperMixin, TestCase):
    def test_cached_method(self):
        """Caching expensive methods by arguments"""
        mock = CacheMock()
        args = ('arg1',)
        kwargs = {'arg2': 2}
        for _ in range(5):
            self.assertEqual(mock.needs_caching(*args, **kwargs), 'result')
        mock.expensive_method.assert_called_once()
        self.assertTrue(hasattr(mock, 'cached_data'))
        key = (*args, *kwargs.values())
        self.assertEqual(
            mock.cached_data.get('needs_caching', {}).get(key),
            'result'
        )

        # cached_data is set/passed from outside
        mock.expensive_method.reset_mock()
        mock.cached_data = {'needs_caching': {key: 'another_result'}}
        for _ in range(5):
            self.assertEqual(mock.needs_caching(*args, **kwargs), 'another_result')
        mock.expensive_method.assert_not_called()
        self.assertTrue(hasattr(mock, 'cached_data'))
        key = (*args, *kwargs.values())
        self.assertEqual(
            mock.cached_data.get('needs_caching', {}).get(key),
            'another_result'
        )

    def test_require_lock(self):
        """PostgreSQL locking decorator"""
        mock = LockMock()
        settings.DEBUG = True
        mock.needs_lock()
        self.assertEqual(len(connection.queries), 1)
        self.assertEqual(connection.queries[0]['sql'], f'LOCK TABLE {Shop._meta.db_table} IN EXCLUSIVE MODE')


# Mock classes

class LockMock(Mock):
    @require_lock(Shop, 'EXCLUSIVE')    # Model does not matter
    def needs_lock(self):
        pass

class CacheMock:
    expensive_method = Mock(return_value='result')

    @cached_method
    def needs_caching(self, arg1, arg2):
        return self.expensive_method()
