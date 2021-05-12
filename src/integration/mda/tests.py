from datetime import datetime, date, timedelta

from django.test import TestCase
from rest_framework.test import APITestCase

from src.base.tests.factories import (
    EmploymentFactory,
    ShopFactory,
    UserFactory,
)
from src.integration.mda.integration import MdaIntegrationHelper
from src.util.mixins.tests import TestsHelperMixin
from src.util.utils import generate_user_token


class TestMdaIntegration(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_shop = ShopFactory(code='base')
        cls.division1 = ShopFactory(parent=cls.base_shop, code='division1', latitude=None, longitude=None)
        cls.region1 = ShopFactory(parent=cls.division1, code='region1', latitude=None, longitude=None)
        cls.shop1 = ShopFactory(parent=cls.region1, code='shop1')
        cls.employment1_1 = EmploymentFactory(shop=cls.shop1)
        cls.employment1_2 = EmploymentFactory(shop=cls.shop1)
        cls.shop2 = ShopFactory(parent=cls.region1, code='shop2', email=None)
        cls.employment2_1 = EmploymentFactory(shop=cls.shop2)
        cls.employment2_2 = EmploymentFactory(shop=cls.shop2)

    def test_get_data(self):
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        self.assertEqual(len(data['divisions']), 1)
        self.assertEqual(len(data['regions']), 1)
        self.assertEqual(len(data['shops']), 2)
        s1_data = list(filter(lambda s: self.shop1.id == s['id'], data['shops']))[0]
        self.assertEqual(s1_data['active'], True)

    def test_shop_without_employments_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop3')
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        self.assertFalse(any(shop.id == s['id'] for s in data['shops']))

    def test_shop_without_code_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code=None)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        self.assertFalse(any(shop.id == s['id'] for s in data['shops']))

    def test_shop_closed_less_than_half_year_ago_in_data_and_active_is_false(self):
        shop = ShopFactory(parent=self.region1, code='shop', dt_closed=date.today() - timedelta(days=10))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        self.assertTrue(any(shop.id == s['id'] for s in data['shops']))
        s_data = list(filter(lambda s: shop.id == s['id'], data['shops']))[0]
        self.assertEqual(s_data['active'], False)

    def test_shop_deleted_less_than_half_year_ago_in_data_and_active_is_false(self):
        shop = ShopFactory(parent=self.region1, code='shop', dttm_deleted=datetime.today() - timedelta(days=10))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        self.assertTrue(any(shop.id == s['id'] for s in data['shops']))
        s_data = list(filter(lambda s: shop.id == s['id'], data['shops']))[0]
        self.assertEqual(s_data['active'], False)

    def test_shop_closed_more_than_half_year_ago_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop', dt_closed=date.today() - timedelta(days=365))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        self.assertFalse(any(shop.id == s['id'] for s in data['shops']))

    def test_shop_more_more_than_half_year_ago_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop', dttm_deleted=datetime.today() - timedelta(days=365))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        self.assertFalse(any(shop.id == s['id'] for s in data['shops']))

    def test_is_all_day_true(self):
        shop = ShopFactory(
            parent=self.region1, code='shop',
            tm_open_dict='{"all":"00:00:00"}', tm_close_dict='{"all":"00:00:00"}',
        )
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        s_data = list(filter(lambda s: shop.id == s['id'], data['shops']))[0]
        self.assertEqual(s_data['allDay'], True)

    def test_is_all_day_false(self):
        shop = ShopFactory(
            parent=self.region1, code='shop',
            tm_open_dict='{"all":"08:00:00"}', tm_close_dict='{"all":"22:00:00"}',
        )
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        s_data = list(filter(lambda s: shop.id == s['id'], data['shops']))[0]
        self.assertEqual(s_data['allDay'], False)

    def test_correct_director_login_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop')
        director = EmploymentFactory(shop=shop)
        shop.director = director.employee.user
        shop.save()
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        s_data = list(filter(lambda s: shop.id == s['id'], data['shops']))[0]
        self.assertEqual(s_data['directorLogin'], director.employee.user.username)

    def test_correct_regionId_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop')
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        data = mda_integration_helper._get_data()
        s_data = list(filter(lambda s: shop.id == s['id'], data['shops']))[0]
        self.assertEqual(s_data['regionId'], self.region1.id)


class TestCaseInsensitiveAuth(TestsHelperMixin, APITestCase):
    lowered_username = 'efimenkomv'

    @classmethod
    def setUpTestData(cls):
        cls.shop = ShopFactory(code='shop')
        cls.user = UserFactory(username='EfimenkoMV')
        cls.employment = EmploymentFactory(shop=cls.shop, user=cls.user)

    def test_case_sensitive_login_by_default(self):
        resp = self.client.post('/api/v1/auth/', data=self.dump_data({
            'username': self.lowered_username,
            'token': generate_user_token(self.lowered_username),
        }), content_type='application/json')
        self.assertContains(
            response=resp,
            text='Невозможно войти с предоставленными учетными данными.',
            status_code=400,
        )

    def test_case_insensitive_login_with_specified_settings(self):
        with self.settings(CASE_INSENSITIVE_AUTH=True):
            resp = self.client.post('/api/v1/auth/', data=self.dump_data({
                'username': self.lowered_username,
                'token': generate_user_token(self.lowered_username),
            }), content_type='application/json')
            self.assertContains(
                response=resp,
                text='token',
                status_code=200,
            )

    def test_signin_token_case_sensitive_by_default(self):
            resp = self.client.post('/rest_api/auth/signin_token/', data=self.dump_data({
                'username': self.lowered_username,
                'token': generate_user_token(self.lowered_username),
            }), content_type='application/json')
            self.assertContains(
                response=resp,
                text='Нет такого пользователя',
                status_code=400,
            )

    def test_signin_token_case_insensitive_with_specified_settings(self):
        with self.settings(CASE_INSENSITIVE_AUTH=True):
            resp = self.client.post('/rest_api/auth/signin_token/', data=self.dump_data({
                'username': self.lowered_username,
                'token': generate_user_token(self.lowered_username),
            }), content_type='application/json')
            self.assertContains(
                response=resp,
                text='data',
                status_code=200,
            )
