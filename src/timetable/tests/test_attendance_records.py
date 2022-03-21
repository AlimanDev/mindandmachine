from datetime import timedelta, time, datetime, date

from django.utils.timezone import now
from rest_framework.test import APITestCase

from src.base.models import (
    Employment,
    Employee,
    Network,
)
from src.timetable.models import (
    WorkerDay,
    AttendanceRecords,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    EmploymentWorkType,
    WorkerDayType,
)
from src.timetable.tests.factories import WorkTypeFactory, WorkerDayFactory, WorkerDayTypeFactory
from src.timetable.vacancy.utils import (
    confirm_vacancy,
)
from src.util.mixins.tests import TestsHelperMixin

class TestAttendanceRecords(TestsHelperMixin, APITestCase):

    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = '/rest_api/worker_day/'
        cls.url_approve = '/rest_api/worker_day/approve/'
        cls.dt = now().date()

        cls.create_departments_and_users()

        cls.worker_day_plan_approved = WorkerDayFactory(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=False,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(cls.dt, time(20, 0, 0)),
        )
        cls.worker_day_plan_not_approved = WorkerDayFactory(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=False,
            is_approved=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(cls.dt, time(20, 0, 0)),
        )
        cls.worker_day_fact_approved = WorkerDayFactory(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=True,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(8, 12, 23)),
            dttm_work_end=datetime.combine(cls.dt, time(20, 2, 1)),
            parent_worker_day=cls.worker_day_plan_approved,
            closest_plan_approved=cls.worker_day_plan_approved,
        )
        cls.worker_day_fact_not_approved = WorkerDayFactory(
            shop=cls.shop,
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt,
            is_fact=True,
            is_approved=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(cls.dt, time(7, 58, 0)),
            dttm_work_end=datetime.combine(cls.dt, time(19, 59, 1)),
            closest_plan_approved=cls.worker_day_plan_approved,
        )
        cls.network.trust_tick_request = True
        cls.network.save()

    def test_attendancerecords_update(self):
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        tm_end = datetime.combine(self.dt, time(21, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start)

        tm_start2 = datetime.combine(self.dt, time(7, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start2,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        # проверяем, что время начала рабочего дня не перезаписалось
        self.assertNotEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start2)
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_start, tm_start)

        AttendanceRecords.objects.create(
            dttm=tm_end,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )
        self.assertEqual(WorkerDay.objects.get(id=self.worker_day_fact_approved.id).dttm_work_end, tm_end)

    def test_attendancerecords_create(self):
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            employee=self.employee3,
        )
        self.assertFalse(wd.exists())
        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user3
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=False,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee3,
            source=WorkerDay.SOURCE_AUTO_FACT,
        )

        self.assertTrue(wd.exists())
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee3,
        )

        self.assertTrue(wd.exists())
        wd = wd.first()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(21, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user3
        )
        self.assertEqual(WorkerDay.objects.get(id=wd.id).dttm_work_end, datetime.combine(self.dt, time(21, 0, 0)))

    def test_attendancerecords_not_approved_fact_create(self):
        self.worker_day_fact_not_approved.parent_worker_day_id = self.worker_day_fact_approved.parent_worker_day_id
        self.worker_day_fact_not_approved.save()

        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(6, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(6, 0, 0)),
            dttm_work_end=None,
            employee=self.employee2
        )

        self.assertTrue(wd.exists())

    def test_attendancerecords_no_fact_create(self):
        self.network.skip_leaving_tick = True
        self.network.save()

        self.worker_day_fact_not_approved.delete()
        self.worker_day_fact_approved.delete()

        AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt, time(20, 0, 0)),
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2,
        )
        wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=datetime.combine(self.dt, time(20, 0, 0)),
            dttm_work_end=None,
            employee=self.employee2,
        )

        self.assertTrue(wd.exists())
        wd = wd.first()

        ar = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt + timedelta(days=1), time(6, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.dttm_work_end, ar.dttm)

        wd.dttm_work_end = None
        wd.save()
        ar2 = AttendanceRecords.objects.create(
            dttm=datetime.combine(self.dt + timedelta(days=3), time(20, 0, 0)),
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop,
            user=self.user2
        )

        new_wd = WorkerDay.objects.filter(
            dt=self.dt + timedelta(days=3),
            is_fact=True,
            is_approved=True,
            dttm_work_start=None,
            dttm_work_end=ar2.dttm,
            employee=self.employee2
        ).first()
        self.assertIsNotNone(new_wd)
        self.assertTrue(new_wd.employment.id, self.employment2.id)

    def test_set_workday_type_for_existing_empty_types(self):
        WorkerDay.objects.filter(id=self.worker_day_fact_approved.id).update(
            type_id=WorkerDay.TYPE_EMPTY,
            dttm_work_start=None,
            dttm_work_end=None,
        )
        WorkerDayCashboxDetails.objects.filter(worker_day_id=self.worker_day_fact_approved.id).delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )

        fact_approved = WorkerDay.objects.get(id=self.worker_day_fact_approved.id)
        self.assertEqual(fact_approved.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(fact_approved.dttm_work_start, tm_start)
        self.assertEqual(fact_approved.dttm_work_end, None)
        fact_worker_day_details = fact_approved.worker_day_details.all()
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)

    def test_set_is_vacancy_as_True_if_shops_are_different(self):
        self.worker_day_fact_approved.delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user8
        )

        new_wd = WorkerDay.objects.filter(
            dt=self.dt,
            is_fact=True,
            is_approved=True,
            dttm_work_start=tm_start,
            dttm_work_end=None,
            employee=self.employee8,
        ).last()
        self.assertEqual(new_wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(new_wd.dttm_work_start, tm_start)
        self.assertEqual(new_wd.dttm_work_end, None)
        self.assertEqual(new_wd.is_vacancy, True)

    def test_create_attendance_records_for_different_shops(self):
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.delete()

        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        ar = AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        wd = WorkerDay.objects.filter(
            employee=ar.employee,
            is_fact=True,
            is_approved=True,
            dt=tm_start.date()
        ).first()
        self.assertIsNotNone(wd)
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, None)
        self.assertEqual(wd.is_vacancy, True)

        tm_end = datetime.combine(self.dt, time(12, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_end,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop2,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, tm_end)
        self.assertEqual(wd.is_vacancy, True)

        tm_start2 = datetime.combine(self.dt, time(13, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start2,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop3,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, tm_end)
        self.assertEqual(wd.is_vacancy, True)

        tm_end2 = datetime.combine(self.dt, time(20, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_end2,
            type=AttendanceRecords.TYPE_LEAVING,
            shop=self.shop3,
            user=self.user2
        )
        wd.refresh_from_db()
        self.assertEqual(wd.type_id, WorkerDay.TYPE_WORKDAY)
        self.assertEqual(wd.dttm_work_start, tm_start)
        self.assertEqual(wd.dttm_work_end, tm_end2)
        self.assertEqual(wd.is_vacancy, True)

    def test_fact_work_type_received_from_plan_approved(self):
        self.worker_day_fact_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)

    def test_fact_work_type_received_from_plan_approved_when_shop_differs(self):
        self.worker_day_fact_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.select_related('work_type')
        self.assertEqual(len(plan_worker_day_details), 1)
        # shop2 wt
        WorkType.objects.create(
            shop=self.shop2,
            work_type_name=plan_worker_day_details[0].work_type.work_type_name,
        )
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2,
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertNotEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)
        self.assertEqual(
            fact_worker_day_details[0].work_type.work_type_name_id,
            plan_worker_day_details[0].work_type.work_type_name_id,
        )

    def test_fact_work_type_received_from_employment_if_there_is_no_plan(self):
        work_type_name = WorkTypeName.objects.create(
            name='Повар',
            network=self.network,
        )
        work_type_name2 = WorkTypeName.objects.create(
            name='Продавец',
            network=self.network,
        )
        work_type = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name,
        )
        work_type2 = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name2,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type,
            priority=10,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type2,
            priority=5,
        )
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, work_type.id)

    def test_work_type_created_for_holiday(self):
        work_type_name = WorkTypeName.objects.create(
            name='Повар',
            network=self.network,
        )
        work_type = WorkType.objects.create(
            shop=self.shop2,
            work_type_name=work_type_name,
        )
        EmploymentWorkType.objects.create(
            employment=self.employment2,
            work_type=work_type,
            priority=10,
        )
        self.worker_day_fact_approved.delete()
        self.worker_day_plan_approved.worker_day_details.all().delete()
        WorkerDay.objects.filter(id=self.worker_day_plan_approved.id).update(
            type_id=WorkerDay.TYPE_HOLIDAY,
            dttm_work_start=None,
            dttm_work_end=None,
        )
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertEqual(fact_worker_day_details[0].work_type_id, work_type.id)

    def test_dt_changed_to_prev(self):
        self.worker_day_fact_approved.delete()
        record1 = AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            type=AttendanceRecords.TYPE_COMING,
            dttm=datetime.combine(self.dt, time(17, 54)),
        )
        record2 = AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            type=AttendanceRecords.TYPE_LEAVING,
            dttm=datetime.combine(self.dt + timedelta(1), time(1, 54)),
        )
        self.assertEqual(record1.dt, self.dt)
        self.assertEqual(record2.dt, self.dt)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        wd = WorkerDay.objects.filter(is_fact=True, is_approved=True).first()
        self.assertEqual(wd.dttm_work_start, datetime.combine(self.dt, time(17, 54)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(self.dt + timedelta(1), time(1, 54)))

    def test_create_second_record_for_prev_day_when_prev_fact_closed(self):
        self.worker_day_fact_approved.dt = self.dt
        self.worker_day_fact_approved.dttm_work_start = datetime.combine(self.dt, time(18, 34))
        self.worker_day_fact_approved.dttm_work_end = datetime.combine(self.dt + timedelta(1), time(1, 2))
        self.worker_day_fact_approved.save()
        AttendanceRecords.objects.create(
            shop_id=self.worker_day_fact_approved.shop_id,
            user_id=self.worker_day_fact_approved.employee.user_id,
            dttm=datetime.combine(self.dt + timedelta(1), time(1, 5)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).count(), 1)
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, is_approved=True).first().dttm_work_end,
                         datetime.combine(self.dt + timedelta(1), time(1, 5)))

    def test_create_att_record_and_update_not_approved(self):
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(11, 5)),
            type=AttendanceRecords.TYPE_COMING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee__user_id=self.user1.id).count(), 2)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, employee=self.employee1)
        wd_approved = WorkerDay.objects.get(is_approved=True, is_fact=True, employee=self.employee1)
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, employee=self.employee1)
        wd_approved.refresh_from_db()
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_end, datetime.combine(self.dt, time(14, 54)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(19, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd_not_approved = WorkerDay.objects.get(is_approved=False, is_fact=True, employee=self.employee1)
        wd_approved.refresh_from_db()
        self.assertEqual(wd_not_approved.dttm_work_start, datetime.combine(self.dt, time(11, 5)))
        self.assertEqual(wd_not_approved.dttm_work_end, datetime.combine(self.dt, time(19, 54)))
        self.assertEqual(wd_not_approved.dttm_work_start, wd_approved.dttm_work_start)

    def test_create_record_no_replace_not_approved_fact(self):
        self.network.skip_leaving_tick = False
        self.network.save()
        wd = WorkerDayFactory(
            dt=self.dt,
            employee_id=self.employment1.employee_id,
            employment=self.employment1,
            shop_id=self.employment1.shop_id,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(10, 5)),
            dttm_work_end=datetime.combine(self.dt, time(20, 10)),
            created_by=self.user1,
            last_edited_by=self.user1,
            is_fact=True,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 1)
        AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(WorkerDay.objects.filter(is_fact=True, employee=self.employee1).count(), 2)
        wd.refresh_from_db()
        self.assertEqual(wd.dttm_work_start, datetime.combine(self.dt, time(10, 5)))
        self.assertEqual(wd.dttm_work_end, datetime.combine(self.dt, time(20, 10)))
        self.assertTrue(WorkerDay.objects.filter(is_fact=True, is_approved=True, dt=self.dt, employee=self.employee1).exists())

    def test_create_attendance_record_fill_employment(self):
        attr = AttendanceRecords.objects.create(
            shop_id=self.employment1.shop_id,
            user_id=self.employment1.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(attr.employee_id, self.employment1.employee_id)
        self.assertEqual(attr.dt, self.dt)
        WorkerDay.objects.update_or_create(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            is_approved=True,
            is_fact=False,
            defaults={
                'employment': self.employment2,
                'type_id': WorkerDay.TYPE_WORKDAY,
                'shop_id': self.employment2.shop_id,
                'dttm_work_start': datetime.combine(self.dt, time(10, 5)),
                'dttm_work_end': datetime.combine(self.dt, time(20, 10)),
            }
        )
        attr = AttendanceRecords.objects.create(
            shop_id=self.employment2.shop_id,
            user_id=self.employment2.employee.user_id,
            dttm=datetime.combine(self.dt, time(14, 54)),
        )
        self.assertEqual(attr.employee_id, self.employment2.employee_id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_COMING)

    def test_create_attendance_record_with_two_near_workdays(self):
        WorkerDay.objects.update_or_create(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            is_approved=True,
            is_fact=False,
            defaults={
                'employment': self.employment2,
                'type_id': WorkerDay.TYPE_WORKDAY,
                'shop': self.shop,
                'dttm_work_start': datetime.combine(self.dt, time(10)),
                'dttm_work_end': datetime.combine(self.dt, time(16)),
            }
        )
        self.second_employee = Employee.objects.create(
            user=self.user2,
            tabel_code='1234',
        )
        self.second_employment = Employment.objects.create(
            employee=self.second_employee,
            shop_id=self.employment2.shop_id,
        )
        WorkerDay.objects.create(
            dt=self.dt,
            employee=self.second_employee,
            is_approved=True,
            is_fact=False,
            employment=self.second_employment,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt, time(16)),
            dttm_work_end=datetime.combine(self.dt, time(22)),
        )
        attr = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(self.dt, time(15, 40)),
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(attr.employee_id, self.employment2.employee_id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_LEAVING)
        attr = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=datetime.combine(self.dt, time(15, 41)),
            type=AttendanceRecords.TYPE_COMING,
        )
        self.assertEqual(attr.employee_id, self.second_employee.id)
        self.assertEqual(attr.dt, self.dt)
        self.assertEqual(attr.type, AttendanceRecords.TYPE_COMING)

    def test_calc_day_and_night_work_hours_when_night_hours_is_less_than_half_of_break_time(self):
        self.worker_day_fact_approved.dttm_work_start = datetime.combine(self.dt, time(16))
        self.worker_day_fact_approved.dttm_work_end = datetime.combine(self.dt, time(22, 15))
        self.worker_day_fact_approved.save()
        total, day, night = self.worker_day_fact_approved.calc_day_and_night_work_hours()
        self.assertEqual(total, 5.25)
        self.assertEqual(day, 5.25)
        self.assertEqual(night, 0.0)

    def test_calc_day_and_night_work_hours_with_round_algo(self):
        self.network.allowed_interval_for_late_arrival = timedelta(minutes=5)
        self.network.allowed_interval_for_early_departure = timedelta(minutes=5)
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.round_work_hours_alg = Network.ROUND_TO_HALF_AN_HOUR
        self.network.save()
        self.breaks.value = '[]'
        self.breaks.save()
        self.shop.refresh_from_db()

        revision_type = WorkerDayTypeFactory(
            code='RV',
            name='Ревизия',
            short_name='РЕВ',
            html_color='#009E9A',
            use_in_plan=True,
            use_in_fact=True,
            excel_load_code='РВ',
            is_dayoff=False,
            is_work_hours=False,
            is_reduce_norm=False,
            show_stat_in_days=True,
            show_stat_in_hours=True,
        )

        plan_worker_day = WorkerDayFactory(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            type_id=revision_type.code,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(19)),
            dttm_work_end=datetime.combine(self.dt, time(23)),
            is_fact=False,
            is_approved=True,
        )

        fact_worker_day = WorkerDayFactory(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            type_id=revision_type.code,
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(19)),
            dttm_work_end=datetime.combine(self.dt, time(22, 54)),
            is_fact=True,
            is_approved=True,
            closest_plan_approved=plan_worker_day,
        )

        total, day, night = fact_worker_day.calc_day_and_night_work_hours()
        self.assertEqual(total, 4)
        self.assertEqual(day, 3)
        self.assertEqual(night, 1)

        fact_worker_day.dttm_work_end = datetime.combine(self.dt, time(22, 29))
        fact_worker_day.save()
        total, day, night = fact_worker_day.calc_day_and_night_work_hours()
        self.assertEqual(total, 3.5)
        self.assertEqual(day, 3)
        self.assertEqual(night, 0.5)
        
        fact_worker_day.dttm_work_start = datetime.combine(self.dt, time(19, 20))
        fact_worker_day.save()
        total, day, night = fact_worker_day.calc_day_and_night_work_hours()
        self.assertEqual(total, 3)
        self.assertEqual(day, 2.5)
        self.assertEqual(night, 0.5)

        self.breaks.value = '[[0, 3600, [40]]]'
        self.breaks.save()
        self.shop.refresh_from_db()

        fact_worker_day.dttm_work_start = datetime.combine(self.dt, time(19))
        fact_worker_day.dttm_work_end = datetime.combine(self.dt, time(22, 50))
        fact_worker_day.save()
        total, day, night = fact_worker_day.calc_day_and_night_work_hours()
        self.assertEqual(total, 3)
        self.assertEqual(day, 2.33)
        self.assertEqual(night, 0.67)

        fact_worker_day.dttm_work_start = datetime.combine(self.dt, time(19, 30))
        fact_worker_day.save()
        total, day, night = fact_worker_day.calc_day_and_night_work_hours()
        self.assertEqual(total, 2.5)
        self.assertEqual(day, 1.83)
        self.assertEqual(night, 0.67)

        self.breaks.value = '[[0, 3600, [30]]]'
        self.breaks.save()
        self.shop.refresh_from_db()

        fact_worker_day.save()
        total, day, night = fact_worker_day.calc_day_and_night_work_hours()
        self.assertEqual(total, 3)
        self.assertEqual(day, 2.25)
        self.assertEqual(night, 0.75)

        fact_worker_day.dttm_work_start = datetime.combine(self.dt, time(19))
        fact_worker_day.save()
        total, day, night = fact_worker_day.calc_day_and_night_work_hours()
        self.assertEqual(total, 3.5)
        self.assertEqual(day, 2.75)
        self.assertEqual(night, 0.75)


    def test_two_facts_created_when_there_are_two_plans(self):
        WorkerDay.objects.filter(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
        ).delete()
        WorkerDayFactory(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            is_approved=True,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt, time(10)),
            dttm_work_end=datetime.combine(self.dt, time(13)),
        )
        WorkerDayFactory(
            dt=self.dt,
            employee_id=self.employment2.employee_id,
            employment=self.employment2,
            is_approved=True,
            is_fact=False,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.shop,
            dttm_work_start=datetime.combine(self.dt, time(19)),
            dttm_work_end=datetime.combine(self.dt, time(22)),
        )

        dttm_start1 = datetime.combine(self.dt, time(9, 54))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_start1,
            type=AttendanceRecords.TYPE_COMING,
        )
        dttm_end1 = datetime.combine(self.dt, time(13, 2))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_end1,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertTrue(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            dttm_work_start=dttm_start1,
            dttm_work_end=dttm_end1,
            is_fact=True,
            is_approved=True,
        ).exists())

        dttm_start2 = datetime.combine(self.dt, time(18, 56))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_start2,
            type=AttendanceRecords.TYPE_COMING,
        )
        dttm_end2 = datetime.combine(self.dt, time(22, 6))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=dttm_end2,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertTrue(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            dttm_work_start=dttm_start2,
            dttm_work_end=dttm_end2,
            is_fact=True,
            is_approved=True,
        ).exists())
        self.assertEqual(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            is_fact=True,
            is_approved=True,
        ).count(), 2)
        self.assertEqual(WorkerDay.objects.filter(
            employee_id=self.employment2.employee_id,
            dt=self.dt,
            is_fact=True,
            is_approved=False,
        ).count(), 2)

    def test_there_is_no_redundant_fact_approved_created_on_att_record_recalc(self):
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_plan_approved.id,
                self.worker_day_plan_not_approved.id,
            ],
        ).update(
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(10)),
            dttm_work_end=datetime.combine(self.dt, time(20)),
        )
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_fact_approved.id,
                self.worker_day_fact_not_approved.id,
            ],
        ).delete()
        fact_dttm_start = datetime.combine(self.dt, time(9, 57))
        ar_start = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_start,
            type=AttendanceRecords.TYPE_COMING,
        )

        fact_qs = WorkerDay.objects.filter(
            employee_id=ar_start.employee_id,
            dt=self.dt,
            dttm_work_start=fact_dttm_start,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
        )
        fact_approved_qs = fact_qs.filter(is_approved=True)
        fact_approved = fact_approved_qs.get()
        fact_not_approved_qs = fact_qs.filter(is_approved=False)
        fact_not_approved = fact_not_approved_qs.get()
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertIsNone(fact_not_approved.last_edited_by_id)
        # при отметке должен был проставиться closest_plan_approved
        self.assertEqual(fact_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)

        manual_fact_dttm_end = datetime.combine(self.dt, time(20))
        resp = self._change_wd_data(fact_not_approved.id, data_to_change={'dttm_work_end': manual_fact_dttm_end})
        self.assertEqual(resp.status_code, 200)
        fact_not_approved.refresh_from_db()
        self.assertEqual(fact_not_approved.dttm_work_end, manual_fact_dttm_end)
        self.assertEqual(fact_not_approved.closest_plan_approved_id, self.worker_day_plan_approved.id)
        resp = self._approve(
            shop_id=fact_not_approved.shop_id,
            is_fact=True,
            dt_from=self.dt,
            dt_to=self.dt,
            employee_ids=[fact_not_approved.employee_id],
        )
        self.assertEqual(resp.status_code, 200)
        fact_not_approved.refresh_from_db()
        self.assertTrue(fact_not_approved.is_approved)
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertEqual(fact_not_approved.last_edited_by_id, self.user1.id)
        self.assertFalse(WorkerDay.objects.filter(id=fact_approved.id).exists())
        fact_approved = fact_not_approved
        fact_not_approved = fact_not_approved_qs.get()
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertEqual(fact_not_approved.last_edited_by_id, self.user1.id)
        # после подтв. факта должен быть проставлен closest_plan_approved в новом факте подтвежденном (бывшем черновике)
        self.assertEqual(fact_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)
        ar_start.refresh_from_db()

        new_plan_dttm_end = datetime.combine(self.dt, time(19))
        resp = self._change_wd_data(
            self.worker_day_plan_not_approved.id, data_to_change={'dttm_work_end': new_plan_dttm_end})
        self.assertEqual(resp.status_code, 200)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertEqual(self.worker_day_plan_not_approved.dttm_work_end, new_plan_dttm_end)
        resp = self._approve(
            shop_id=self.worker_day_plan_not_approved.shop_id,
            is_fact=False,
            dt_from=self.dt,
            dt_to=self.dt,
            employee_ids=[self.worker_day_plan_not_approved.employee_id],
        )
        self.assertEqual(resp.status_code, 200)
        self.worker_day_plan_not_approved.refresh_from_db()
        self.assertTrue(self.worker_day_plan_not_approved.is_approved)
        plan_approved = self.worker_day_plan_not_approved
        # после подтверждения плана должен проставиться новый план подтвержденный (бывшый план черновик)
        fact_approved.refresh_from_db()
        self.assertEqual(fact_approved.closest_plan_approved.id, plan_approved.id)

        self.assertTrue(WorkerDay.objects.filter(id=fact_approved.id).exists())
        self.assertTrue(WorkerDay.objects.filter(id=fact_not_approved.id).exists())

        # TODO: проверка, что автоматический пересчет факта на основе отметок запустится
        # пока вызовем пересчет отметки вручную
        ar_start.save()
        self.assertEqual(fact_approved_qs.count(), 1)  # не должен создаться дополнительный факт

    def test_night_shift_leaving_tick_diff_more_than_in_settings(self):
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_plan_approved.id,
                self.worker_day_plan_not_approved.id,
            ],
        ).update(
            dt=self.dt,
            dttm_work_start=datetime.combine(self.dt, time(8)),
            dttm_work_end=datetime.combine(self.dt + timedelta(days=1), time(7)),
        )
        WorkerDay.objects.filter(
            id__in=[
                self.worker_day_fact_approved.id,
                self.worker_day_fact_not_approved.id,
            ],
        ).delete()

        fact_dttm_start = datetime.combine(self.dt, time(7, 47))
        ar_start = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_start,
            type=AttendanceRecords.TYPE_COMING,
        )

        fact_qs = WorkerDay.objects.filter(
            employee_id=ar_start.employee_id,
            dt=self.dt,
            dttm_work_start=fact_dttm_start,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
        )
        fact_approved_qs = fact_qs.filter(is_approved=True)
        fact_approved = fact_approved_qs.get()
        fact_not_approved_qs = fact_qs.filter(is_approved=False)
        fact_not_approved = fact_not_approved_qs.get()
        self.assertIsNone(fact_not_approved.created_by_id)
        self.assertIsNone(fact_not_approved.last_edited_by_id)
        # при отметке должен был проставиться closest_plan_approved
        self.assertEqual(fact_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)
        self.assertEqual(fact_not_approved.closest_plan_approved.id, self.worker_day_plan_approved.id)

        fact_dttm_end = datetime.combine(self.dt + timedelta(days=1), time(1, 40))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_end,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        fact_approved.refresh_from_db()
        self.assertEqual(fact_approved.dttm_work_end, fact_dttm_end)

    def test_att_record_when_vacation_and_workday_in_plan(self):
        workday_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_WORKDAY,
        ).get()
        vacation_type = WorkerDayType.objects.filter(
            code=WorkerDay.TYPE_VACATION,
        ).get()
        vacation_type.get_work_hours_method = WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL
        vacation_type.is_work_hours = True
        vacation_type.is_dayoff = True
        vacation_type.save()
        vacation_type.allowed_additional_types.add(workday_type)

        WorkerDay.objects.all().delete()
        dt = date(2021, 6, 7)

        for is_approved in [True, False]:
            WorkerDayFactory(
                is_approved=is_approved,
                is_fact=False,
                shop=self.shop2,
                employment=self.employment2,
                employee=self.employee2,
                work_hours=timedelta(hours=10),
                dt=dt,
                type_id=WorkerDay.TYPE_VACATION,
            )
            WorkerDayFactory(
                is_approved=is_approved,
                is_fact=False,
                shop=self.shop,
                employment=self.employment2,
                employee=self.employee2,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(8)),
                dttm_work_end=datetime.combine(dt, time(22)),
            )
        fact_dttm_start = datetime.combine(dt, time(7, 40))
        ar_start = AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_start,
            type=AttendanceRecords.TYPE_COMING,
        )
        fact_dttm_end = datetime.combine(dt, time(21, 40))
        AttendanceRecords.objects.create(
            shop=self.shop,
            user=self.user2,
            dttm=fact_dttm_end,
            type=AttendanceRecords.TYPE_LEAVING,
        )

        fact_qs = WorkerDay.objects.filter(
            employee_id=ar_start.employee_id,
            dt=dt,
            dttm_work_start=fact_dttm_start,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
        )
        fact_approved_qs = fact_qs.filter(is_approved=True)
        fact_approved = fact_approved_qs.get()
        fact_not_approved_qs = fact_qs.filter(is_approved=False)
        fact_not_approved = fact_not_approved_qs.get()

        self.assertFalse(fact_approved.closest_plan_approved.type.is_dayoff)
        self.assertFalse(fact_not_approved.closest_plan_approved.type.is_dayoff)
        self.assertEqual(fact_approved.dttm_work_start, fact_dttm_start)
        self.assertEqual(fact_approved.dttm_work_end, fact_dttm_end)

    def test_create_attendance_records_when_closest_plan_does_not_exist(self):
        WorkerDay.objects.filter(employee=self.employee3).delete()
        wd_far_approved_fact = WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 9, 21),
            is_approved=True,
            is_fact=True,
            dttm_work_start=datetime(2021, 9, 21, 8, 34),
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        record = AttendanceRecords.objects.create(
            employee=self.employee3,
            user=self.user3,
            dttm=datetime(2021, 11, 12, 21, 23),
            shop=self.shop,
            type=AttendanceRecords.TYPE_LEAVING,
        )
        self.assertEqual(record.dt, date(2021, 11, 12))
        wd_far_approved_fact.refresh_from_db()
        self.assertIsNone(wd_far_approved_fact.dttm_work_end)
        wd_created = WorkerDay.objects.filter(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 11, 12),
            is_approved=True,
            is_fact=True,
            type_id=WorkerDay.TYPE_WORKDAY,
        ).first()
        self.assertIsNotNone(wd_created)
        self.assertIsNone(wd_created.dttm_work_start)
        self.assertEqual(wd_created.dttm_work_end, datetime(2021, 11, 12, 21, 23))

    def test_work_type_created_without_employment_work_type_and_plan(self):
        employment = self.employment5
        dt = date.today()
        work_type = WorkTypeFactory(
            shop_id=employment.shop_id,
            work_type_name__name="Работа",
        )
        WorkerDay.objects.filter(employee_id=employment.employee_id).delete()
        AttendanceRecords.objects.create(
            employee_id=employment.employee_id,
            user_id=self.user5.id,
            type=AttendanceRecords.TYPE_COMING,
            dt=dt,
            dttm=datetime.combine(dt, time(8, 10)),
            shop_id=employment.shop_id,
        )
        wd_fact = WorkerDay.objects.filter(dt=dt, employee_id=employment.employee_id, is_fact=True, is_approved=True).first()
        self.assertIsNotNone(wd_fact)
        details = WorkerDayCashboxDetails.objects.filter(worker_day=wd_fact).first()
        self.assertIsNotNone(details)
        self.assertEqual(details.work_type_id, work_type.id)
        WorkerDay.objects.filter(employee_id=employment.employee_id).delete()
        AttendanceRecords.objects.create(
            employee_id=employment.employee_id,
            user_id=self.user5.id,
            type=AttendanceRecords.TYPE_LEAVING,
            dt=dt,
            dttm=datetime.combine(dt, time(19, 10)),
            shop_id=employment.shop_id,
        )
        wd_fact = WorkerDay.objects.filter(dt=dt, employee_id=employment.employee_id, is_fact=True, is_approved=True).first()
        self.assertIsNotNone(wd_fact)
        details = WorkerDayCashboxDetails.objects.filter(worker_day=wd_fact).first()
        self.assertIsNotNone(details)
        self.assertEqual(details.work_type_id, work_type.id)

    def test_set_closest_plan_approved_on_confirm_vacancy_to_worker(self):
        ShopMonthStat.objects.create(
            shop=self.shop,
            dt=date(2021, 9, 1),
            dttm_status_change=now(),
            status=ShopMonthStat.READY,
            is_approved=True,
        )
        WorkerDay.objects.filter(employee=self.employee3).delete()
        WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 9, 21),
            is_approved=True,
            is_fact=False,
            type_id=WorkerDay.TYPE_HOLIDAY,
        )
        wd_approved_fact = WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 9, 21),
            is_approved=True,
            is_fact=True,
            dttm_work_start=datetime(2021, 9, 21, 8, 34),
            dttm_work_end=datetime(2021, 9, 21, 20, 15),
            type_id=WorkerDay.TYPE_WORKDAY,
            closest_plan_approved=None,
        )
        vacancy = WorkerDay.objects.create(
            shop=self.shop,
            is_vacancy=True,
            dt=date(2021, 9, 21),
            is_approved=True,
            is_fact=False,
            dttm_work_start=datetime(2021, 9, 21, 9),
            dttm_work_end=datetime(2021, 9, 21, 20),
            type_id=WorkerDay.TYPE_WORKDAY,
            closest_plan_approved=None,
        )
        confirm_vacancy(vacancy_id=vacancy.id, user=self.employee3.user, employee_id=self.employee3.id)
        wd_approved_fact.refresh_from_db()
        self.assertIsNotNone(wd_approved_fact.closest_plan_approved_id)
        self.assertEqual(wd_approved_fact.closest_plan_approved_id, vacancy.id)

    def test_set_closest_plan_approved_on_leaving_att_record(self):
        ShopMonthStat.objects.create(
            shop=self.shop,
            dt=date(2021, 9, 1),
            dttm_status_change=now(),
            status=ShopMonthStat.READY,
            is_approved=True,
        )
        WorkerDay.objects.filter(employee=self.employee3).delete()
        plan_approved = WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 9, 21),
            is_approved=True,
            is_fact=False,
            dttm_work_start=datetime(2021, 9, 21, 8, 34),
            dttm_work_end=datetime(2021, 9, 21, 20, 15),
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        wd_approved_fact = WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            shop=self.shop,
            dt=date(2021, 9, 21),
            is_approved=True,
            is_fact=True,
            dttm_work_start=datetime(2021, 9, 21, 8, 34),
            type_id=WorkerDay.TYPE_WORKDAY,
            closest_plan_approved=None,
        )
        AttendanceRecords.objects.create(
            employee_id=self.employee3.id,
            user_id=self.user3.id,
            type=AttendanceRecords.TYPE_LEAVING,
            dt=date(2021, 9, 21),
            dttm=datetime.combine(date(2021, 9, 21), time(20)),
            shop_id=self.shop.id,
        )

        wd_approved_fact.refresh_from_db()
        self.assertEqual(wd_approved_fact.dttm_work_end, datetime.combine(date(2021, 9, 21), time(20)))
        self.assertIsNotNone(wd_approved_fact.closest_plan_approved_id)
        self.assertEqual(wd_approved_fact.closest_plan_approved_id, plan_approved.id)

    def test_dont_set_deleted_work_type_received_by_plan_work_type(self):
        self.worker_day_fact_approved.delete()
        tm_start = datetime.combine(self.dt, time(6, 0, 0))
        plan_worker_day_details = self.worker_day_plan_approved.worker_day_details.select_related('work_type')
        self.assertEqual(len(plan_worker_day_details), 1)
        # shop2 deleted wt
        WorkType.objects.create(
            shop=self.shop2,
            work_type_name=plan_worker_day_details[0].work_type.work_type_name,
            dttm_deleted=self.dt - timedelta(days=15),
        )
        wt_not_deleted = WorkType.objects.create(
            shop=self.shop2,
            work_type_name= WorkTypeName.objects.create(
                network=self.network,
                name='shop2 not deleted wt',
            )
        )
        AttendanceRecords.objects.create(
            dttm=tm_start,
            type=AttendanceRecords.TYPE_COMING,
            shop=self.shop2,
            user=self.user2,
        )
        fact_approved = WorkerDay.objects.get(
            is_fact=True,
            is_approved=True,
            employee=self.employee2,
            dt=self.dt,
        )
        fact_worker_day_details = fact_approved.worker_day_details.all()
        self.assertEqual(len(fact_worker_day_details), 1)
        self.assertNotEqual(fact_worker_day_details[0].work_type_id, plan_worker_day_details[0].work_type_id)
        self.assertEqual(
            fact_worker_day_details[0].work_type.id,
            wt_not_deleted.id,
        )

    def test_details_not_created_for_worker_day_type_without_details(self):
        WorkerDay.objects.filter(employee=self.employee4).delete()
        dt = date.today()
        wd_plan = WorkerDayFactory(
            type_id=WorkerDay.TYPE_QUALIFICATION,
            dttm_work_start=datetime.combine(dt, time(12)),
            dttm_work_end=datetime.combine(dt, time(20)),
            employee=self.employee4,
            employment=self.employment4,
            shop=self.shop,
            dt=dt,
            is_approved=True,
            is_fact=False,
        )
        self.assertEqual(wd_plan.worker_day_details.count(), 0)
        record = AttendanceRecords.objects.create(
            dt=dt,
            dttm=datetime.combine(dt, time(11, 55)),
            shop=self.shop,
            user=self.user4,
            employee=self.employee4,
            type=AttendanceRecords.TYPE_COMING,
        )
        fact_wd = getattr(record, 'fact_wd', None)
        self.assertIsNotNone(fact_wd)
        self.assertEqual(fact_wd.closest_plan_approved_id, wd_plan.id)
        self.assertEqual(fact_wd.type_id, WorkerDay.TYPE_QUALIFICATION)
        self.assertEqual(fact_wd.worker_day_details.count(), 0)
        self.assertEqual(WorkerDayCashboxDetails.objects.filter(worker_day__employee=self.employee4).count(), 0)    
