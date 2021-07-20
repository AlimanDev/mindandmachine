from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from src.base.tests.factories import UserFactory, EmploymentFactory, ShopFactory, EmployeeFactory
from src.timetable.models import WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from src.timetable.utils import CleanWdaysHelper
from src.util.mixins.tests import TestsHelperMixin


class TestCleanWdays(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt_now = timezone.now().today()
        cls.user = UserFactory()
        cls.employee = EmployeeFactory(user=cls.user)
        cls.shop = ShopFactory()

    def test_empl_cleaned_when_there_is_no_other_active_empl(self):
        empl = EmploymentFactory(
            employee=self.employee, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        wd = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt_now,
            employee=self.employee,
            shop=self.shop,
            employment=empl,
            type=WorkerDay.TYPE_WORKDAY,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 0, 'skipped': 0, 'not_found': 0, 'empl_cleaned': 1})
        self.assertTrue(WorkerDay.objects_with_excluded.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertIsNone(wd.employment_id)

    def test_wday_inactive_employment_replaced_with_active_employment_from_the_same_shop(self):
        inactive_empl = EmploymentFactory(
            employee=self.employee, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        active_empl = EmploymentFactory(
            employee=self.employee, shop=self.shop,
            dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=50),
        )
        wd = WorkerDayFactory(
            dt=self.dt_now + timedelta(days=1),
            employee=self.employee,
            shop=self.shop,
            employment=inactive_empl,
            type=WorkerDay.TYPE_WORKDAY,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 1, 'skipped': 0, 'not_found': 0, 'empl_cleaned': 0})
        self.assertTrue(WorkerDay.objects_with_excluded.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, active_empl.id)
        self.assertFalse(wd.is_vacancy)

    def test_empl_cleaned_if_is_plan_and_shops_differs_and_is_vacancy_false(self):
        inactive_empl = EmploymentFactory(
            employee=self.employee, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        other_shop = ShopFactory()
        EmploymentFactory(
            employee=self.employee, shop=other_shop,
            dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=50),
        )
        wd = WorkerDayFactory(
            dt=self.dt_now + timedelta(days=1),
            employee=self.employee,
            shop=self.shop,
            employment=inactive_empl,
            type=WorkerDay.TYPE_WORKDAY,
            is_vacancy=False,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False, clean_plan_empl=True)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 0, 'skipped': 0, 'not_found': 0, 'empl_cleaned': 1})
        self.assertTrue(WorkerDay.objects_with_excluded.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertIsNone(wd.employment_id)
        self.assertFalse(wd.is_vacancy)

    def test_wday_inactive_employment_replaced_with_active_employment_from_other_shop_if_is_vacancy_true(self):
        inactive_empl = EmploymentFactory(
            employee=self.employee, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        other_shop = ShopFactory()
        active_empl_in_other_shop = EmploymentFactory(
            employee=self.employee, shop=other_shop,
            dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=50),
        )
        wd = WorkerDayFactory(
            dt=self.dt_now + timedelta(days=1),
            employee=self.employee,
            shop=self.shop,
            employment=inactive_empl,
            type=WorkerDay.TYPE_WORKDAY,
            is_vacancy=True,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 1, 'skipped': 0, 'not_found': 0, 'empl_cleaned': 0})
        self.assertTrue(WorkerDay.objects_with_excluded.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, active_empl_in_other_shop.id)
        self.assertTrue(wd.is_vacancy)

    # def test_shop_id_and_is_vacancy_cleaned_for_holiday(self):
    #     other_shop = ShopFactory()
    #     active_empl_in_other_shop = EmploymentFactory(
    #         employee=self.employee, shop=other_shop,
    #         dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=50),
    #     )
    #     wd = WorkerDayFactory(
    #         dt=self.dt_now + timedelta(days=1),
    #         employee=self.employee,
    #         shop=self.shop,
    #         employment=active_empl_in_other_shop,
    #         type=WorkerDay.TYPE_HOLIDAY,
    #         is_vacancy=True,
    #     )
    #
    #     clean_wdays_helper = CleanWdaysHelper(only_logging=False)
    #     with mock.patch.object(transaction, 'on_commit', lambda t: t()):
    #         results = clean_wdays_helper.run()
    #
    #     self.assertDictEqual(results, {'changed': 1, 'skipped': 0, 'not_found': 0, 'empl_cleaned': 0})
    #     self.assertTrue(WorkerDay.objects_with_excluded.filter(id=wd.id).exists())
    #     wd.refresh_from_db()
    #     self.assertEqual(wd.employment_id, active_empl_in_other_shop.id)
    #     self.assertFalse(wd.is_vacancy)
    #     self.assertIsNone(wd.shop_id)

    def test_fact_not_deleted_but_empl_cleaned_if_there_is_no_active_empl(self):
        empl = EmploymentFactory(
            employee=self.employee, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        wd = WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt_now,
            employee=self.employee,
            shop=self.shop,
            employment=empl,
            type=WorkerDay.TYPE_WORKDAY,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 0, 'skipped': 0, 'not_found': 0, 'empl_cleaned': 1})
        self.assertTrue(WorkerDay.objects_with_excluded.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertIsNone(wd.employment_id)
