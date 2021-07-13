from datetime import datetime, date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from src.base.models import Employment
from src.base.tests.factories import (
    EmploymentFactory,
    ShopFactory,
    UserFactory,
    EmployeeFactory,
    GroupFactory,
    WorkerPositionFactory,
)
from src.integration.mda.integration import MdaIntegrationHelper
from src.integration.models import VMdaUsers
from src.timetable.models import WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from src.util.utils import generate_user_token


class TestMdaIntegration(TestsHelperMixin, TestCase):
    maxDiff = None

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

    def test_get_orgstruct_data(self):
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        self.assertEqual(len(orgstruct_data['divisions']), 1)
        self.assertEqual(len(orgstruct_data['regions']), 1)
        self.assertEqual(len(orgstruct_data['shops']), 2)
        s1_orgstruct_data = list(filter(lambda s: self.shop1.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s1_orgstruct_data['active'], True)

    def test_shop_without_employments_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop3')
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        self.assertFalse(any(shop.id == s['id'] for s in orgstruct_data['shops']))

    def test_shop_without_code_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code=None)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        self.assertFalse(any(shop.id == s['id'] for s in orgstruct_data['shops']))

    def test_shop_closed_less_than_half_year_ago_in_data_and_active_is_false(self):
        shop = ShopFactory(parent=self.region1, code='shop', dt_closed=date.today() - timedelta(days=10))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        self.assertTrue(any(shop.id == s['id'] for s in orgstruct_data['shops']))
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['active'], False)

    def test_shop_deleted_less_than_half_year_ago_in_data_and_active_is_false(self):
        shop = ShopFactory(parent=self.region1, code='shop', dttm_deleted=datetime.today() - timedelta(days=10))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        self.assertTrue(any(shop.id == s['id'] for s in orgstruct_data['shops']))
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['active'], False)

    def test_shop_closed_more_than_half_year_ago_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop', dt_closed=date.today() - timedelta(days=365))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        self.assertFalse(any(shop.id == s['id'] for s in orgstruct_data['shops']))

    def test_shop_more_more_than_half_year_ago_not_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop', dttm_deleted=datetime.today() - timedelta(days=365))
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        self.assertFalse(any(shop.id == s['id'] for s in orgstruct_data['shops']))

    def test_is_all_day_true(self):
        shop = ShopFactory(
            parent=self.region1, code='shop',
            tm_open_dict='{"all":"00:00:00"}', tm_close_dict='{"all":"00:00:00"}',
        )
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['allDay'], True)

    def test_is_all_day_false(self):
        shop = ShopFactory(
            parent=self.region1, code='shop',
            tm_open_dict='{"all":"08:00:00"}', tm_close_dict='{"all":"22:00:00"}',
        )
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['allDay'], False)

    def test_correct_director_login_in_data(self):
        group_director = GroupFactory(name='Директор', code='director')
        position_director = WorkerPositionFactory(name='Директор', group=group_director)
        shop = ShopFactory(parent=self.region1, code='shop')
        director = EmploymentFactory(shop=shop, position=position_director)
        shop.director = director.employee.user
        shop.save()
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['directorLogin'], director.employee.user.username)

        users_data = mda_integration_helper._get_users_data()
        director_data = list(filter(lambda u: director.employee.user_id == u['id'], users_data))[0]
        self.assertEqual(director_data['active'], True)
        self.assertEqual(director_data['orgLevel'], 'SHOP')
        self.assertEqual(director_data['orgUnits'], [str(shop.id)])
        self.assertEqual(director_data['admin'], False)
        self.assertEqual(director_data['shopDirector'], True)

    def test_multiple_directors(self):
        group_director = GroupFactory(name='Директор', code='director')
        position_director = WorkerPositionFactory(name='Директор', group=group_director)
        shop = ShopFactory(parent=self.region1, code='shop')
        director = EmploymentFactory(shop=shop, position=position_director)
        director2 = EmploymentFactory(shop=shop, position=position_director)
        shop.director = director.employee.user
        shop.save()
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['directorLogin'], director.employee.user.username)

        users_data = mda_integration_helper._get_users_data()
        director_data = list(filter(lambda u: director.employee.user_id == u['id'], users_data))[0]
        self.assertEqual(director_data['shopDirector'], True)

        director2_data = list(filter(lambda u: director2.employee.user_id == u['id'], users_data))[0]
        self.assertEqual(director2_data['shopDirector'], False)

        shop.director = director2.employee.user
        shop.save()

        users_data = mda_integration_helper._get_users_data()
        director_data = list(filter(lambda u: director.employee.user_id == u['id'], users_data))[0]
        self.assertEqual(director_data['shopDirector'], False)

        director2_data = list(filter(lambda u: director2.employee.user_id == u['id'], users_data))[0]
        self.assertEqual(director2_data['shopDirector'], True)

    def test_multiple_levels(self):
        region = ShopFactory(parent=self.division1, code='region')
        shop = ShopFactory(parent=region, code='shop')
        group_director = GroupFactory(name='Директор', code='director')
        group_urs = GroupFactory(name='УРС', code='urs')
        position_director = WorkerPositionFactory(name='Директор', group=group_director)
        position_urs = WorkerPositionFactory(name='Директор', group=group_urs)
        user = UserFactory()
        employee = EmployeeFactory(user=user)
        _region_director = EmploymentFactory(employee=employee, shop=region, position=position_urs)
        shop_director = EmploymentFactory(employee=employee, shop=shop, position=position_director)

        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['directorLogin'], shop_director.employee.user.username)

        users_data = mda_integration_helper._get_users_data()
        self.assertEqual(len(users_data), 5)
        user_data = list(filter(lambda u: user.id == u['id'], users_data))[0]
        self.assertEqual(user_data['shopDirector'], True)
        self.assertEqual(user_data['orgLevel'], 'SHOP')
        self.assertEqual(user_data['userChecklistsOrganizer'], False)

    def test_userChecklistsOrganizer(self):
        region = ShopFactory(parent=self.division1, code='region')
        group_urs = GroupFactory(name='УРС', code='urs')
        position_urs = WorkerPositionFactory(name='Директор', group=group_urs)
        user = UserFactory()
        employee = EmployeeFactory(user=user)
        _region_director = EmploymentFactory(employee=employee, shop=region, position=position_urs)

        mda_integration_helper = MdaIntegrationHelper()

        users_data = mda_integration_helper._get_users_data()
        self.assertEqual(len(users_data), 5)
        user_data = list(filter(lambda u: user.id == u['id'], users_data))[0]
        self.assertEqual(user_data['shopDirector'], False)
        self.assertEqual(user_data['orgLevel'], 'REGION')
        self.assertEqual(user_data['userChecklistsOrganizer'], True)

    def test_orgUnits_null_for_company_level(self):
        group_admin = GroupFactory(name='Администратор', code='admin')
        user = UserFactory()
        employee = EmployeeFactory(user=user)
        _admin_employment = EmploymentFactory(employee=employee, shop=self.base_shop, function_group=group_admin)

        mda_integration_helper = MdaIntegrationHelper()
        users_data = mda_integration_helper._get_users_data()
        self.assertEqual(len(users_data), 5)
        user_data = list(filter(lambda u: user.id == u['id'], users_data))[0]
        self.assertEqual(user_data['orgLevel'], 'COMPANY')
        self.assertEqual(user_data['orgUnits'],  None)

    def test_surveyAdmin_for_admin_true_for_oters_false(self):
        group_admin = GroupFactory(name='Администратор', code='admin')
        group_worker = GroupFactory(name='Сотрудник', code='worker')
        user_admin = UserFactory()
        user_worker = UserFactory()
        employee_admin = EmployeeFactory(user=user_admin)
        employee_worker = EmployeeFactory(user=user_worker)
        _admin_employment = EmploymentFactory(
            employee=employee_admin, shop=self.base_shop, function_group=group_admin)
        _worker_employment = EmploymentFactory(
            employee=employee_worker, shop=self.base_shop, function_group=group_worker)

        mda_integration_helper = MdaIntegrationHelper()
        users_data = mda_integration_helper._get_users_data()
        self.assertEqual(len(users_data), 6)
        user_admin_data = list(filter(lambda u: user_admin.id == u['id'], users_data))[0]
        self.assertEqual(user_admin_data['admin'], True)
        self.assertEqual(user_admin_data['surveyAdmin'],  True)

        user_worker_data = list(filter(lambda u: user_worker.id == u['id'], users_data))[0]
        self.assertEqual(user_worker_data['admin'], False)
        self.assertEqual(user_worker_data['surveyAdmin'],  False)

    def test_correct_regionId_in_data(self):
        shop = ShopFactory(parent=self.region1, code='shop')
        EmploymentFactory(shop=shop)
        mda_integration_helper = MdaIntegrationHelper()
        orgstruct_data = mda_integration_helper._get_orgstruct_data()
        s_orgstruct_data = list(filter(lambda s: shop.id == s['id'], orgstruct_data['shops']))[0]
        self.assertEqual(s_orgstruct_data['regionId'], self.region1.id)

    def test_there_is_no_user_with_dt_fired_90_days_ago(self):
        Employment.objects.all().delete()
        shop = ShopFactory(parent=self.region1, code='shop')
        EmploymentFactory(
            shop=shop,
            dt_hired=datetime.now() - timedelta(days=220),
            dt_fired=datetime.now() - timedelta(days=90),
        )
        mda_integration_helper = MdaIntegrationHelper()
        users_data = mda_integration_helper._get_users_data()
        self.assertEqual(len(users_data), 0)

    def test_there_is_user_with_dt_fired_30_days_ago(self):
        Employment.objects.all().delete()
        shop = ShopFactory(parent=self.region1, code='shop')
        EmploymentFactory(
            shop=shop,
            dt_hired=datetime.now() - timedelta(days=220),
            dt_fired=datetime.now() - timedelta(days=30),
        )
        mda_integration_helper = MdaIntegrationHelper()
        users_data = mda_integration_helper._get_users_data()
        self.assertEqual(len(users_data), 1)


class TestVMdaUsers(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.base_shop = ShopFactory(code='base')
        cls.division1 = ShopFactory(parent=cls.base_shop, code='division1', latitude=None, longitude=None)
        cls.region1 = ShopFactory(parent=cls.division1, code='region1', latitude=None, longitude=None)
        cls.shop1 = ShopFactory(parent=cls.region1, code='shop1')
        cls.group_director = GroupFactory(code='director', name='Директор')
        cls.group_worker = GroupFactory(code='worker', name='Сотрудник')
        cls.position_director = WorkerPositionFactory(group=cls.group_director, name='Директор', code='director')
        cls.position_seller = WorkerPositionFactory(group=cls.group_worker, name='Продавец-кассир', code='seller')
        cls.dt_now = timezone.now()

    def test_2_directors_and_1_of_them_has_vacation(self):
        """
        2 директора: 1 из них в отпуске
        DIR должен проставляться директору, который не в отпуске
        """
        user_director1 = UserFactory()
        employee_director1 = EmployeeFactory(user=user_director1)
        employment_director1 = EmploymentFactory(
            employee=employee_director1, shop=self.shop1, position=self.position_director)
        user_director2 = UserFactory()
        employee_director2 = EmployeeFactory(user=user_director2)
        employment_director2 = EmploymentFactory(
            employee=employee_director2, shop=self.shop1, position=self.position_director)
        director1_vacation = WorkerDayFactory(
            dt=self.dt_now,
            employee=employee_director1,
            employment=None,
            shop=self.shop1,
            type=WorkerDay.TYPE_VACATION,
            is_fact=False,
            is_approved=True,
        )
        users_dict = {u.code: u for u in VMdaUsers.objects.all()}
        self.assertEqual(len(users_dict), 2)

        director1 = users_dict[employment_director1.code]
        self.assertEqual(director1.role, 'MANAGER')

        director2 = users_dict[employment_director2.code]
        self.assertEqual(director2.role, 'DIR')

        director1_vacation.delete()

        # director2 vacation
        WorkerDayFactory(
            dt=self.dt_now,
            employee=employee_director2,
            employment=None,
            shop=self.shop1,
            type=WorkerDay.TYPE_VACATION,
            is_fact=False,
            is_approved=True,
        )
        users_dict = {u.code: u for u in VMdaUsers.objects.all()}
        self.assertEqual(len(users_dict), 2)

        director1 = users_dict[employment_director1.code]
        self.assertEqual(director1.role, 'DIR')

        director2 = users_dict[employment_director2.code]
        self.assertEqual(director2.role, 'MANAGER')

    def test_add_tmp_director_employment_to_not_director_user(self):
        """
        Добавление временного скрытого трудоустройства директора сотруднику, который не являается директором
        При этом основной директор на больничном
        DIR должен проставиться сотруднику, который временно выполняет роль директора
        """
        user_director = UserFactory()
        employee_director = EmployeeFactory(user=user_director)
        employment_director = EmploymentFactory(
            employee=employee_director, shop=self.shop1, position=self.position_director)
        user_seller = UserFactory()
        employee_seller = EmployeeFactory(user=user_seller)
        EmploymentFactory(
            employee=employee_seller, shop=self.shop1, position=self.position_seller)
        employment_tmp_director = EmploymentFactory(
            is_visible=False,
            dt_hired=self.dt_now - timedelta(days=5), dt_fired=self.dt_now + timedelta(days=5),
            employee=employee_seller, shop=self.shop1, position=self.position_director)
        director_sickness = WorkerDayFactory(
            dt=self.dt_now,
            employee=employee_director,
            employment=None,
            shop=self.shop1,
            type=WorkerDay.TYPE_SICK,
            is_fact=False,
            is_approved=True,
        )
        users_dict = {u.code: u for u in VMdaUsers.objects.all()}
        self.assertEqual(len(users_dict), 3)

        director = users_dict[employment_director.code]
        self.assertEqual(director.role, 'MANAGER')

        seller = users_dict[employment_tmp_director.code]
        self.assertEqual(seller.role, 'DIR')

        director_sickness.delete()

        users_dict = {u.code: u for u in VMdaUsers.objects.all()}
        self.assertEqual(len(users_dict), 3)

        director = users_dict[employment_director.code]
        self.assertEqual(director.role, 'DIR')

        seller = users_dict[employment_tmp_director.code]
        self.assertEqual(seller.role, 'MANAGER')

    def test_2_directors_different_norm_work_hours_and_is_visible(self):
        """
        2 активных директора
        Один видимый ставка 50, другой невидимый ставка 100
        DIR проставляется с приоритетом по видимости TODO: правильно?
        """

        user_director1 = UserFactory()
        employee_director1 = EmployeeFactory(user=user_director1)
        employment_director1 = EmploymentFactory(
            employee=employee_director1, shop=self.shop1, position=self.position_director, is_visible=False)
        user_director2 = UserFactory()
        employee_director2 = EmployeeFactory(user=user_director2)
        employment_director2 = EmploymentFactory(
            employee=employee_director2, shop=self.shop1, position=self.position_director, norm_work_hours=50)

        users_dict = {u.code: u for u in VMdaUsers.objects.all()}
        self.assertEqual(len(users_dict), 2)

        director1 = users_dict[employment_director1.code]
        self.assertEqual(director1.role, 'MANAGER')

        director2 = users_dict[employment_director2.code]
        self.assertEqual(director2.role, 'DIR')


class TestCaseInsensitiveAuth(TestsHelperMixin, APITestCase):
    lowered_username = 'efimenkomv'

    @classmethod
    def setUpTestData(cls):
        cls.shop = ShopFactory(code='shop')
        cls.user = UserFactory(username='EfimenkoMV')
        cls.employee = EmployeeFactory(user=cls.user, tabel_code='0000-0001')
        cls.employment = EmploymentFactory(shop=cls.shop, employee=cls.employee)

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
