from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from src.base.tests.factories import UserFactory, EmploymentFactory, ShopFactory
from src.timetable.models import WorkerDay
from src.timetable.tests.factories import WorkerDayFactory
from src.timetable.utils import CleanWdaysHelper
from src.util.mixins.tests import TestsHelperMixin


class TestCleanWdays(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt_now = timezone.now().today()
        cls.user = UserFactory()
        cls.shop = ShopFactory()

    def test_wday_deleted_when_there_is_no_other_active_empl(self):
        empl = EmploymentFactory(
            user=self.user, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        wd = WorkerDayFactory(
            dt=self.dt_now,
            worker=self.user,
            shop=self.shop,
            employment=empl,
            type=WorkerDay.TYPE_WORKDAY,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 0, 'deleted': 1, 'skipped': 0, 'not_found': 0})
        self.assertFalse(WorkerDay.objects.filter(id=wd.id).exists())

    def test_wday_inactive_employment_replaced_with_active_employment_from_the_same_shop(self):
        inactive_empl = EmploymentFactory(
            user=self.user, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        active_empl = EmploymentFactory(
            user=self.user, shop=self.shop,
            dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=50),
        )
        wd = WorkerDayFactory(
            dt=self.dt_now + timedelta(days=1),
            worker=self.user,
            shop=self.shop,
            employment=inactive_empl,
            type=WorkerDay.TYPE_WORKDAY,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 1, 'deleted': 0, 'skipped': 0, 'not_found': 0})
        self.assertTrue(WorkerDay.objects.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, active_empl.id)
        self.assertFalse(wd.is_vacancy)

    def test_wday_inactive_employment_replaced_with_active_employment_from_other_shop(self):
        inactive_empl = EmploymentFactory(
            user=self.user, shop=self.shop,
            dt_hired=self.dt_now - timedelta(days=30), dt_fired=self.dt_now - timedelta(days=1),
        )
        other_shop = ShopFactory()
        active_empl_in_other_shop = EmploymentFactory(
            user=self.user, shop=other_shop,
            dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=50),
        )
        wd = WorkerDayFactory(
            dt=self.dt_now + timedelta(days=1),
            worker=self.user,
            shop=self.shop,
            employment=inactive_empl,
            type=WorkerDay.TYPE_WORKDAY,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 1, 'deleted': 0, 'skipped': 0, 'not_found': 0})
        self.assertTrue(WorkerDay.objects.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, active_empl_in_other_shop.id)
        self.assertTrue(wd.is_vacancy)

    def test_shop_id_and_is_vacancy_cleaned_for_holiday(self):
        other_shop = ShopFactory()
        active_empl_in_other_shop = EmploymentFactory(
            user=self.user, shop=other_shop,
            dt_hired=self.dt_now, dt_fired=self.dt_now + timedelta(days=50),
        )
        wd = WorkerDayFactory(
            dt=self.dt_now + timedelta(days=1),
            worker=self.user,
            shop=self.shop,
            employment=active_empl_in_other_shop,
            type=WorkerDay.TYPE_HOLIDAY,
            is_vacancy=True,
        )

        clean_wdays_helper = CleanWdaysHelper(only_logging=False)
        results = clean_wdays_helper.run()

        self.assertDictEqual(results, {'changed': 1, 'deleted': 0, 'skipped': 0, 'not_found': 0})
        self.assertTrue(WorkerDay.objects.filter(id=wd.id).exists())
        wd.refresh_from_db()
        self.assertEqual(wd.employment_id, active_empl_in_other_shop.id)
        self.assertFalse(wd.is_vacancy)
        self.assertIsNone(wd.shop_id)
