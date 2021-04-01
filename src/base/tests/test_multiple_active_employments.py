from datetime import date, time, datetime

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from src.base.tests.factories import ShopFactory, UserFactory, GroupFactory, EmploymentFactory, NetworkFactory
from src.recognition.models import Tick
from src.timetable.models import WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin


class MultipleActiveEmploymentsSupportMixin(TestsHelperMixin):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.root_shop = ShopFactory(network=cls.network)
        cls.shop1 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP1',
            network=cls.network,
        )
        cls.shop2 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP2',
            network=cls.network,
        )
        cls.shop3 = ShopFactory(
            parent=cls.root_shop,
            name='SHOP3',
            network=cls.network,
        )
        cls.user1 = UserFactory(email='dir@example.com', network=cls.network)
        cls.user2 = UserFactory(email='urs@example.com', network=cls.network)

        cls.group1 = GroupFactory(network=cls.network)

        # первая цифра -- user_id, вторая цифра -- shop_id, третья -- порядковый номер
        cls.employment1_1_1 = EmploymentFactory(
            user=cls.user1, shop=cls.shop1, function_group=cls.group1, network=cls.network
        )
        cls.employment1_1_2 = EmploymentFactory(
            user=cls.user1, shop=cls.shop2, function_group=cls.group1, network=cls.network, norm_work_hours=50
        )
        cls.employment2_2_1 = EmploymentFactory(
            user=cls.user2, shop=cls.shop2, function_group=cls.group1, network=cls.network
        )
        cls.employment2_3_1 = EmploymentFactory(
            user=cls.user2, shop=cls.shop3, function_group=cls.group1, network=cls.network, norm_work_hours=50
        )
        cls.dt = date.today()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, TRUST_TICK_REQUEST=True)
class TestURVTicks(MultipleActiveEmploymentsSupportMixin, APITestCase):
    """
    Проверка работы отметок когда у пользователя несколько активных трудоустройств одновременно
    """
    @classmethod
    def setUpTestData(cls):
        super(TestURVTicks, cls).setUpTestData()
        cls.add_group_perm(cls.group1, 'Tick', 'POST')

    def _make_tick_requests(self, user, shop):
        self.client.force_authenticate(user=user)
        resp_coming = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_COMING, 'shop_code': shop.code}),
            content_type='application/json',
        )
        self.assertEqual(resp_coming.status_code, status.HTTP_200_OK)

        resp_leaving = self.client.post(
            self.get_url('Tick-list'),
            data=self.dump_data({'type': Tick.TYPE_LEAVING, 'shop_code': shop.code}),
            content_type='application/json',
        )
        self.assertEqual(resp_leaving.status_code, status.HTTP_200_OK)

        self.assertEqual(Tick.objects.count(), 2)

        fact_approved = WorkerDay.objects.filter(
            worker=user,
            dt=self.dt,
            is_fact=True,
            is_approved=True,
        ).first()
        self.assertIsNotNone(fact_approved)
        return fact_approved

    def test_get_employment_from_plan(self):
        """
        Получение трудоустройства из плана
        """
        self.client.force_authenticate(user=self.user1)
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            worker=self.user1,
            employment=self.employment1_1_2,
            shop=self.shop1,
            type=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        fact_approved = self._make_tick_requests(self.user1, self.shop1)
        self.assertEqual(fact_approved.employment_id, self.employment1_1_2.id)
        self.assertIsNotNone(fact_approved.dttm_work_start)
        self.assertIsNotNone(fact_approved.dttm_work_end)

    def test_get_employment_for_user2_by_shop2(self):
        """
        Получение трудоустройства с приоритетом по подразделению в случае если нету плана (shop2)
        """
        self.client.force_authenticate(user=self.user2)
        fact_approved = self._make_tick_requests(self.user2, self.shop2)
        self.assertEqual(fact_approved.employment_id, self.employment2_2_1.id)

    def test_get_employment_for_user2_by_shop3(self):
        """
        Получение трудоустройства с приоритетом по подразделению в случае если нету плана (shop3)
        """
        self.client.force_authenticate(user=self.user2)
        fact_approved = self._make_tick_requests(self.user2, self.shop3)
        self.assertEqual(fact_approved.employment_id, self.employment2_3_1.id)

    def test_get_employment_by_max_norm_work_hours_when_multiple_active_empls_in_the_same_shop(self):
        """
        Получение трудоустройства с наибольшей ставкой
        """
        self.client.force_authenticate(user=self.user1)
        fact_approved = self._make_tick_requests(self.user1, self.shop1)
        self.assertEqual(fact_approved.employment_id, self.employment1_1_1.id)
