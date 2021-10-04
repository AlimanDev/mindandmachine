from datetime import time, datetime, timedelta

from django.utils.timezone import now
from rest_framework.test import APITestCase

from src.base.tests.factories import (
    NetworkFactory,
    UserFactory,
    EmploymentFactory,
    ShopSettingsFactory,
    ShopFactory,
    GroupFactory,
    EmployeeFactory,
)
from src.timetable.models import (
    WorkType,
    WorkTypeName,
    WorkerDay,
)
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin


class TestOnlyFactHoursThatInApprovedPlan(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        from src.base.shop.tasks import fill_shop_schedule
        cls.dt = now().date()
        cls.network = NetworkFactory(
            only_fact_hours_that_in_approved_plan=True,
            crop_work_hours_by_shop_schedule=False,
        )
        cls.user = UserFactory(network=cls.network)
        cls.employee = EmployeeFactory(user=cls.user)
        cls.shop_settings = ShopSettingsFactory(
            breaks__value='[[0, 2040, [60]]]')
        cls.shop = ShopFactory(network=cls.network, settings=cls.shop_settings)
        cls.group = GroupFactory(network=cls.network)
        cls.employment = EmploymentFactory(employee=cls.employee, shop=cls.shop, function_group=cls.group)
        fill_shop_schedule(shop_id=cls.shop.id, dt_from=cls.dt, periods=1)
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type = WorkType.objects.create(work_type_name=cls.work_type_name, shop=cls.shop)

    def setUp(self):
        self.shop_settings.breaks.refresh_from_db(fields=['value'])

    def test_zero_work_hours_if_there_is_no_plan_approved_workday(self):
        fact_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        self.assertEqual(fact_approved.work_hours.total_seconds(), 0)

    def test_crop_fact_approved_work_hours_by_plan_approved(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        fact_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 25, 0)),
            closest_plan_approved=plan_approved,
        )
        self.assertEqual(fact_approved.work_hours.total_seconds(), 10 * 3600)

    def test_crop_fact_approved_work_hours_by_plan_approved_with_multiple_wdays_on_one_date(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(14, 0, 0)),
        )
        fact_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(14, 25, 0)),
            closest_plan_approved=plan_approved,
        )
        self.assertEqual(fact_approved.work_hours.total_seconds(), 4 * 3600)

        plan_approved2 = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(18, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(22, 0, 0)),
        )
        fact_approved2 = WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(17, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(22, 24, 0)),
            closest_plan_approved=plan_approved2,
        )
        self.assertEqual(fact_approved2.work_hours.total_seconds(), 3 * 3600)

    def test_crop_fact_not_approved_work_hours_by_plan_approved(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        fact_not_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=False,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 25, 0)),
            closest_plan_approved=plan_approved,
        )
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 10 * 3600)

    def test_crop_fact_not_approved_work_hours_by_plan_approved_with_multiple_wdays_on_one_date(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(14, 0, 0)),
        )
        fact_not_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=False,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(14, 25, 0)),
            closest_plan_approved=plan_approved,
        )
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 4 * 3600)

        plan_approved2 = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(18, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(22, 0, 0)),
        )
        fact_not_approved2 = WorkerDayFactory(
            is_fact=True,
            is_approved=False,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(17, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(22, 24, 0)),
            closest_plan_approved=plan_approved2,
        )
        self.assertEqual(fact_not_approved2.work_hours.total_seconds(), 3 * 3600)

    def test_crop_fact_approved_work_hours_by_plan_approved_created_after_fact(self):
        fact_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 25, 0)),
        )
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )
        fact_approved.refresh_from_db(fields=('work_hours',))
        fact_approved.closest_plan_approved = plan_approved
        fact_approved.save()
        self.assertEqual(fact_approved.work_hours.total_seconds(), 10 * 3600)

    def test_facts_work_hours_recalculated_on_plan_change(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
        )

        fact_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=True,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 35, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 25, 0)),
            closest_plan_approved=plan_approved,
        )
        self.assertEqual(fact_approved.work_hours.total_seconds(), 10 * 3600)

        fact_not_approved = WorkerDayFactory(
            is_fact=True,
            is_approved=False,
            dt=self.dt,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(9, 00, 0)),
            dttm_work_end=datetime.combine(self.dt, time(19, 00, 0)),
            closest_plan_approved=plan_approved,
        )
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 9 * 3600)

        plan_approved.dttm_work_start = datetime.combine(self.dt, time(11, 00, 0))
        plan_approved.dttm_work_end = datetime.combine(self.dt, time(17, 00, 0))
        plan_approved.save()

        fact_approved.refresh_from_db()
        self.assertEqual(fact_approved.work_hours.total_seconds(), 5 * 3600)
        fact_not_approved.refresh_from_db()
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 5 * 3600)

    def test_crop_work_hours_and_use_break_from_plan(self):
        breaks = self.shop_settings.breaks
        breaks.value = '[[0, 359, [0]], [359, 720, [72]]]'
        breaks.save()
        wd_plan = WorkerDay.objects.create(
            employee=self.employee,
            employment=self.employment,
            is_fact=False,
            is_approved=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(12)),
            dttm_work_end=datetime.combine(self.dt, time(18)),
        )
        wd_fact = WorkerDay.objects.create(
            employee=self.employee,
            employment=self.employment,
            is_fact=True,
            is_approved=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(13, 2)),
            dttm_work_end=datetime.combine(self.dt, time(19, 4)),
            closest_plan_approved=wd_plan,
        )
        self.assertGreaterEqual(wd_plan.work_hours, wd_fact.work_hours)
        work_hours = ((wd_fact.dttm_work_end_tabel - wd_fact.dttm_work_start_tabel).total_seconds() / 60) - 72
        self.assertEqual(wd_fact.work_hours, timedelta(minutes=work_hours))

    def test_work_hours_not_negative_if_break_time_greater_than_work_time(self):
        wd = WorkerDay.objects.create(
            employee=self.employee,
            employment=self.employment,
            is_fact=False,
            is_approved=True,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(13, 30)),
            dttm_work_end=datetime.combine(self.dt, time(13, 35)),
        )
        self.assertEqual(wd.work_hours.total_seconds(), 0)
