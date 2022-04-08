from datetime import time, datetime, timedelta

from django.utils.timezone import now
from rest_framework.test import APITestCase

from src.base.tests.factories import (
    NetworkFactory,
    UserFactory,
    EmploymentFactory,
    ShopFactory,
    GroupFactory,
    EmployeeFactory,
    BreakFactory,
    WorkerPositionFactory,
)
from src.timetable.models import (
    WorkType,
    WorkTypeName,
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin


class TestWorkerDayApprove(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url_approve = cls.get_url('WorkerDay-approve')
        cls.today = now().date()
        cls.yesterday = cls.today - timedelta(days=1)
        cls.tomorrow = cls.today + timedelta(days=1)
        cls.breaks = BreakFactory(value='[[0, 2040, [60]]]')
        cls.network = NetworkFactory(
            breaks=cls.breaks,
            only_fact_hours_that_in_approved_plan=False,
            crop_work_hours_by_shop_schedule=False,
        )
        cls.user = UserFactory(network=cls.network)
        cls.employee = EmployeeFactory(user=cls.user)
        cls.shop = ShopFactory(network=cls.network)
        cls.shop2 = ShopFactory(network=cls.network)
        cls.group = GroupFactory(network=cls.network)
        cls.position = WorkerPositionFactory(network=cls.network, group=cls.group)
        cls.employment = EmploymentFactory(employee=cls.employee, shop=cls.shop, position=cls.position)
        cls.work_type_name = WorkTypeName.objects.create(name='Работа', network=cls.network)
        cls.work_type = WorkType.objects.create(work_type_name=cls.work_type_name, shop=cls.shop)
        cls.work_type2 = WorkType.objects.create(work_type_name=cls.work_type_name, shop=cls.shop2)
        cls.add_group_perm(cls.group, 'WorkerDay_approve', 'POST')
        cls.plan_approve_wd_permission = WorkerDayPermission.objects.get(
            graph_type=WorkerDayPermission.PLAN,
            action=WorkerDayPermission.APPROVE,
            wd_type_id=WorkerDay.TYPE_WORKDAY,
        )
        cls.plan_group_approve_wd_permission = GroupWorkerDayPermission.objects.create(
            group=cls.group,
            worker_day_permission=cls.plan_approve_wd_permission,
        )
        cls.fact_approve_wd_permission = WorkerDayPermission.objects.get(
            graph_type=WorkerDayPermission.FACT,
            action=WorkerDayPermission.APPROVE,
            wd_type_id=WorkerDay.TYPE_WORKDAY,
        )
        cls.fact_group_approve_wd_permission = GroupWorkerDayPermission.objects.create(
            group=cls.group,
            worker_day_permission=cls.fact_approve_wd_permission,
        )

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user)

    def test_approve_multiple_wdays_in_plan(self):
        WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(18)),
            dttm_work_end=datetime.combine(self.today, time(22)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )

        approve_data = {
            'shop_id': self.shop.id,
            'is_fact': False,
            'dt_from': self.today,
            'dt_to': self.today,
            'wd_types': [WorkerDay.TYPE_WORKDAY],
        }

        resp = self.client.post(self.url_approve, self.dump_data(approve_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        approved_plan_wdays_qs = WorkerDay.objects.filter(is_fact=False, is_approved=True, shop_id=self.shop.id)
        self.assertEqual(approved_plan_wdays_qs.count(), 2)
        for wd in approved_plan_wdays_qs:
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)

        not_approved_plan_wdays_qs = WorkerDay.objects.filter(is_fact=False, is_approved=False, shop_id=self.shop.id)
        self.assertEqual(not_approved_plan_wdays_qs.count(), 2)
        for wd in not_approved_plan_wdays_qs:
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)

    def test_approve_multiple_wdays_in_fact(self):
        WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(18)),
            dttm_work_end=datetime.combine(self.today, time(22)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )

        approve_data = {
            'shop_id': self.shop.id,
            'is_fact': True,
            'dt_from': self.today,
            'dt_to': self.today,
            'wd_types': [WorkerDay.TYPE_WORKDAY],
        }

        resp = self.client.post(self.url_approve, self.dump_data(approve_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        approved_fact_wdays_qs = WorkerDay.objects.filter(is_fact=True, is_approved=True, shop_id=self.shop.id)
        self.assertEqual(approved_fact_wdays_qs.count(), 2)
        for wd in approved_fact_wdays_qs:
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)

        not_approved_fact_wdays_qs = WorkerDay.objects.filter(is_fact=True, is_approved=False, shop_id=self.shop.id)
        self.assertEqual(not_approved_fact_wdays_qs.count(), 2)
        for wd in not_approved_fact_wdays_qs:
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)

        wd1 = WorkerDay.objects.filter(
            is_fact=True, is_approved=False, shop_id=self.shop.id).order_by('dttm_work_start').first()
        wd1.dttm_work_start = datetime.combine(self.today, time(11))
        wd1.save()

        resp = self.client.post(self.url_approve, self.dump_data(approve_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        approved_fact_wdays_qs = WorkerDay.objects.filter(is_fact=True, is_approved=True, shop_id=self.shop.id)
        self.assertEqual(approved_fact_wdays_qs.count(), 2)
        for wd in approved_fact_wdays_qs:
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)

        not_approved_fact_wdays_qs = WorkerDay.objects.filter(is_fact=True, is_approved=False, shop_id=self.shop.id)
        self.assertEqual(not_approved_fact_wdays_qs.count(), 2)
        for wd in not_approved_fact_wdays_qs:
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)

        wd1.refresh_from_db()
        self.assertTrue(wd1.is_approved)

    def test_days_approved_when_one_day_in_draft_and_two_wdays_in_approved_version(self):
        WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
            dttm_work_start=datetime.combine(self.today, time(18)),
            dttm_work_end=datetime.combine(self.today, time(22)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )

        resp = self._approve(
            self.shop.id,
            is_fact=False,
            dt_from=self.today,
            dt_to=self.today,
            wd_types=[WorkerDay.TYPE_WORKDAY],
        )
        self.assertEqual(resp.status_code, 200)
        # день, которого нету в подтв. версии должен удалиться
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 1)

    def test_approved_only_changed_dates(self):
        plan_approved_yesterday = WorkerDayFactory(
            dt=self.yesterday,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
            dttm_work_start=datetime.combine(self.yesterday, time(10)),
            dttm_work_end=datetime.combine(self.yesterday, time(18)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        plan_approved_today = WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(22)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        plan_approved_tomorrow = WorkerDayFactory(
            dt=self.tomorrow,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
            dttm_work_start=datetime.combine(self.tomorrow, time(10)),
            dttm_work_end=datetime.combine(self.tomorrow, time(20)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        plan_not_approved_yesterday = WorkerDayFactory(
            dt=self.yesterday,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.yesterday, time(10)),
            dttm_work_end=datetime.combine(self.yesterday, time(18)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        plan_not_approved_today = WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(19)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        plan_not_approved_tomorrow = WorkerDayFactory(
            dt=self.tomorrow,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.tomorrow, time(10)),
            dttm_work_end=datetime.combine(self.tomorrow, time(20)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )

        resp = self._approve(
            self.shop.id,
            is_fact=False,
            dt_from=self.today,
            dt_to=self.today,
            wd_types=[WorkerDay.TYPE_WORKDAY],
        )
        self.assertEqual(resp.status_code, 200)

        self.assertFalse(plan_not_approved_yesterday.is_approved)
        self.assertTrue(WorkerDay.objects.filter(id=plan_approved_yesterday.id).exists())
        self.assertFalse(plan_not_approved_tomorrow.is_approved)
        self.assertTrue(WorkerDay.objects.filter(id=plan_approved_tomorrow.id).exists())

        plan_not_approved_today.refresh_from_db()
        self.assertTrue(plan_not_approved_today.is_approved)
        self.assertFalse(WorkerDay.objects.filter(id=plan_approved_today.id).exists())

        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 3)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 3)

    # def test_approved_version_not_deleted_when_there_is_no_draft_data(self):
    #     plan_approved_today = WorkerDayFactory(
    #         dt=self.today,
    #         employee=self.employee,
    #         employment=self.employment,
    #         shop=self.shop,
    #         type_id=WorkerDay.TYPE_WORKDAY,
    #         is_fact=False,
    #         is_approved=True,
    #         dttm_work_start=datetime.combine(self.today, time(10)),
    #         dttm_work_end=datetime.combine(self.today, time(22)),
    #         last_edited_by=self.user,
    #         cashbox_details__work_type=self.work_type,
    #     )
    #
    #     resp = self._approve(
    #         self.shop.id,
    #         is_fact=False,
    #         dt_from=self.today,
    #         dt_to=self.today,
    #         wd_types=[WorkerDay.TYPE_WORKDAY],
    #     )
    #     self.assertEqual(resp.status_code, 200)
    #
    #     self.assertTrue(WorkerDay.objects.filter(id=plan_approved_today.id).exists())
    #     self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 1)
    #     self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 0)

    def test_approve_wdays_for_different_shops(self):
        """
        1. В черновике 1 интервал в своем магазине, другой интервал в чужом магазине (вакансия)
        2. Директор магазина подтверждает график в своем магазине,
            сейчас подтвердяться оба дня (и в своем магазине и в чужом)
            TODO: продумать более гибкие настройки/правила подтверждения?
        """
        plan_not_approved_today1 = WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )
        plan_not_approved_today2 = WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(16)),
            dttm_work_end=datetime.combine(self.today, time(22)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type2,
        )

        resp = self._approve(
            self.shop.id,
            is_fact=False,
            dt_from=self.today,
            dt_to=self.today,
            wd_types=[WorkerDay.TYPE_WORKDAY],
        )
        self.assertEqual(resp.status_code, 200)

        plan_not_approved_today1.refresh_from_db()
        self.assertTrue(plan_not_approved_today1.is_approved)
        plan_not_approved_today2.refresh_from_db()
        self.assertTrue(plan_not_approved_today2.is_approved)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 2)
        for wd in WorkerDay.objects.filter(is_fact=False, is_approved=True):
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 2)
        for wd in WorkerDay.objects.filter(is_fact=False, is_approved=False):
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)

    def test_can_approve_vacancy(self):
        vac_not_approved = WorkerDayFactory(
            dt=self.today,
            employee=None,
            employment=None,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(20)),
            cashbox_details__work_type=self.work_type,
        )
        resp = self._approve(
            self.shop.id,
            is_fact=False,
            dt_from=self.today,
            dt_to=self.today,
            wd_types=[WorkerDay.TYPE_WORKDAY],
            approve_open_vacs=True,
        )
        self.assertEqual(resp.status_code, 200)
        vac_not_approved.refresh_from_db()
        self.assertTrue(vac_not_approved.is_approved)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 1)
        for wd in WorkerDay.objects.filter(is_fact=False, is_approved=True):
            self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day=wd).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 0)

    def test_approve_two_similar_open_vacs(self):
        vac_not_approved1 = WorkerDayFactory(
            dt=self.today,
            employee=None,
            employment=None,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(20)),
            cashbox_details__work_type=self.work_type,
        )
        vac_not_approved2 = WorkerDayFactory(
            dt=self.today,
            employee=None,
            employment=None,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(20)),
            cashbox_details__work_type=self.work_type,
        )
        resp = self._approve(
            self.shop.id,
            is_fact=False,
            dt_from=self.today,
            dt_to=self.today,
            wd_types=[WorkerDay.TYPE_WORKDAY],
            approve_open_vacs=True,
        )
        self.assertEqual(resp.status_code, 200)
        vac_not_approved1.refresh_from_db()
        vac_not_approved2.refresh_from_db()
        self.assertTrue(vac_not_approved1.is_approved)
        self.assertTrue(vac_not_approved2.is_approved)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=True).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(is_fact=False, is_approved=False).count(), 0)

    def test_approve_only_specific_worker_day_types(self):
        plan_not_approved1 = WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_VACATION,
            is_fact=False,
            is_approved=False,
        )
        plan_approved1 = WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop2,
            type_id=WorkerDay.TYPE_VACATION,
            is_fact=False,
            is_approved=True,
        )
        plan_approved2 = WorkerDayFactory(
            dt=self.today,
            employee=self.employee,
            employment=self.employment,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=True,
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            last_edited_by=self.user,
            cashbox_details__work_type=self.work_type,
        )

        resp = self._approve(
            self.shop.id,
            is_fact=False,
            dt_from=self.today,
            dt_to=self.today,
            wd_types=[WorkerDay.TYPE_WORKDAY],
            approve_open_vacs=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(WorkerDay.objects.filter(id=plan_not_approved1.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=plan_approved1.id).exists())
        self.assertFalse(WorkerDay.objects.filter(id=plan_approved2.id).exists())
