import json
from datetime import timedelta, time, datetime, date

from rest_framework.test import APITestCase

from src.apps.base.models import (
    Break,
    Network,
    Employment,
    Region,
    ShopSchedule,
    Shop,
    Employee,
    User,
    WorkerPosition,
)
from src.apps.timetable.models import (
    WorkerDay,
)


class TestFineLogic(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.network = Network.objects.create(name='Test')
        cls.shop = Shop.objects.create(
            name='Shop',
            network=cls.network,
            region=Region.objects.create(name='Def', network=cls.network),
        )
        cls.network.fines_settings = json.dumps(
           {
                r'(.*)?директор|управляющий(.*)?': {
                    'arrive_fines': [[-5, 10, 60], [60, 3600, 120]],
                    'departure_fines': [[-5, 10, 60], [60, 3600, 120]],
                },
                r'(.*)?кладовщик|курьер(.*)?': {
                    'arrive_fines': [[0, 10, 30], [30, 3600, 60]],
                    'departure_fines': [[-10, 10, 30], [60, 3600, 60]],
                },
                r'(.*)?продавец|кассир|менеджер|консультант(.*)?': {
                    'arrive_fines': [[-4, 60, 60], [60, 120, 120]],
                    'departure_fines': [],
                },
            }
        )
        cls.network.save()
        cls.breaks = Break.objects.create(
            name='brk',
            value='[[0, 3600, [30]]]',
            network=cls.network,
        )
        cls.cashier = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Продавец-кассир', breaks=cls.breaks), 'Cashier', 'cashier')
        cls.dir = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Директор Магазина', breaks=cls.breaks), 'Dir', 'dir')
        cls.courier = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Курьер', breaks=cls.breaks), 'Courier', 'courier')
        cls.cleaner = cls._create_user(cls, WorkerPosition.objects.create(network=cls.network, name='Уборщик', breaks=cls.breaks), 'Cleaner', 'cleaner')

    def setUp(self):
        self.network.refresh_from_db()

    def _create_user(self, position, last_name, username):
        user = User.objects.create(
            last_name=last_name,
            username=username,
        )
        employee = Employee.objects.create(
            user=user,
            tabel_code=username,
        )
        employment = Employment.objects.create(
            employee=employee,
            position=position,
            shop=self.shop,
        )
        return user, employee, employment

    def _create_or_update_worker_day(self, employment, dttm_from, dttm_to, is_fact=False, is_approved=True, closest_plan_approved_id=None):
        wd, _ =  WorkerDay.objects.update_or_create(
            employee_id=employment.employee_id,
            is_fact=is_fact,
            is_approved=is_approved,
            dt=dttm_from.date(),
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            defaults=dict(
                dttm_work_start=dttm_from,
                dttm_work_end=dttm_to,
                employment=employment,
            ),
            closest_plan_approved_id=closest_plan_approved_id,
        )
        return wd

    def test_fine_settings(self):
        dt = date.today()
        plan_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEqual(plan_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 53)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEqual(fact_wd_dir.work_hours, timedelta(hours=9, minutes=47))
        fact_wd_dir_bad = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEqual(fact_wd_dir_bad.work_hours, timedelta(hours=7, minutes=34))

        plan_wd_cashier = self._create_or_update_worker_day(self.cashier[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEqual(plan_wd_cashier.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_cashier = self._create_or_update_worker_day(self.cashier[2], datetime.combine(dt, time(9, 55)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_cashier.id)
        self.assertEqual(fact_wd_cashier.work_hours, timedelta(hours=9, minutes=45))
        fact_wd_cashier_bad = self._create_or_update_worker_day(self.cashier[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_cashier.id)
        self.assertEqual(fact_wd_cashier_bad.work_hours, timedelta(hours=8, minutes=34))

        plan_wd_courier = self._create_or_update_worker_day(self.courier[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEqual(plan_wd_courier.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_courier = self._create_or_update_worker_day(self.courier[2], datetime.combine(dt, time(9, 55)), datetime.combine(dt, time(20, 11)), is_fact=True, closest_plan_approved_id=plan_wd_courier.id)
        self.assertEqual(fact_wd_courier.work_hours, timedelta(hours=9, minutes=46))
        fact_wd_courier_bad = self._create_or_update_worker_day(self.courier[2], datetime.combine(dt, time(10, 1)), datetime.combine(dt, time(19, 50)), is_fact=True, closest_plan_approved_id=plan_wd_courier.id)
        self.assertEqual(fact_wd_courier_bad.work_hours, timedelta(hours=8, minutes=19))

        plan_wd_cleaner = self._create_or_update_worker_day(self.cleaner[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEqual(plan_wd_cleaner.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_cleaner = self._create_or_update_worker_day(self.cleaner[2], datetime.combine(dt, time(9, 55)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_cleaner.id)
        self.assertEqual(fact_wd_cleaner.work_hours, timedelta(hours=9, minutes=45))
        fact_wd_cleaner_bad = self._create_or_update_worker_day(self.cleaner[2], datetime.combine(dt, time(10, 5)), datetime.combine(dt, time(19, 50)), is_fact=True, closest_plan_approved_id=plan_wd_cleaner.id)
        self.assertEqual(fact_wd_cleaner_bad.work_hours, timedelta(hours=9, minutes=15))

    def test_facts_work_hours_recalculated_on_plan_change(self):
        dt = date.today()
        plan_approved = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9)), datetime.combine(dt, time(20)))

        fact_approved = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(8, 35)), datetime.combine(dt, time(20, 25)), is_fact=True, closest_plan_approved_id=plan_approved.id)
        self.assertEqual(fact_approved.work_hours.total_seconds(), 11 * 3600 + 20 * 60)

        fact_not_approved = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9)), datetime.combine(dt, time(19)), is_approved=False, is_fact=True, closest_plan_approved_id=plan_approved.id)
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 6 * 3600 + 30 * 60)

        plan_approved.dttm_work_start = datetime.combine(dt, time(11, 00, 0))
        plan_approved.dttm_work_end = datetime.combine(dt, time(17, 00, 0))
        plan_approved.save()

        fact_approved.refresh_from_db()
        self.assertEqual(fact_approved.work_hours.total_seconds(), 11 * 3600 + 20 * 60)
        fact_not_approved.refresh_from_db()
        self.assertEqual(fact_not_approved.work_hours.total_seconds(), 9 * 3600 + 30 * 60)

    def test_fine_settings_only_work_hours_that_in_plan(self):
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()
        dt = date.today()
        plan_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEqual(plan_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 53)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEqual(fact_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir_bad = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEqual(fact_wd_dir_bad.work_hours, timedelta(hours=7, minutes=30))

    def test_fine_settings_crop_work_hours_by_shop_schedule(self):
        self.network.crop_work_hours_by_shop_schedule = True
        self.network.save()
        dt = date.today()
        ShopSchedule.objects.create(
            dt=dt,
            shop=self.shop,
            opens='10:00:00',
            closes='20:00:00',
        )
        plan_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(10)), datetime.combine(dt, time(20)))
        self.assertEqual(plan_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 53)), datetime.combine(dt, time(20, 10)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEqual(fact_wd_dir.work_hours, timedelta(hours=9, minutes=30))
        fact_wd_dir_bad = self._create_or_update_worker_day(self.dir[2], datetime.combine(dt, time(9, 56)), datetime.combine(dt, time(20)), is_fact=True, closest_plan_approved_id=plan_wd_dir.id)
        self.assertEqual(fact_wd_dir_bad.work_hours, timedelta(hours=7, minutes=30))

    def _test_fine_case(self, tm_work_start_plan, tm_work_end_plan, tm_work_start_fact, tm_work_end_fact, work_hours):
        WorkerDay.objects.all().delete()
        dt = date.today()
        plan_wd = self._create_or_update_worker_day(
            self.cashier[2], 
            datetime.combine(dt, tm_work_start_plan), 
            datetime.combine(dt, tm_work_end_plan), 
        )
        fact_wd = self._create_or_update_worker_day(
            self.cashier[2], 
            datetime.combine(dt, tm_work_start_fact), 
            datetime.combine(dt, tm_work_end_fact), 
            is_fact=True,
            closest_plan_approved_id=plan_wd.id,
        )
        self.assertEqual(fact_wd.work_hours, work_hours)
        return fact_wd

    def test_fine_settings_round(self):
        self.network.fines_settings = json.dumps(
           {
                r'.*': {
                    'arrive_step': 30,
                    'departure_step': 30,
                },
            }
        )
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.save()

        self._test_fine_case(time(8), time(20), time(7, 55), time(20, 1), timedelta(hours=11, minutes=30))
        self._test_fine_case(time(8), time(20), time(8), time(20), timedelta(hours=11, minutes=30))
        self._test_fine_case(time(8), time(20), time(10), time(19), timedelta(hours=8, minutes=30))
        self._test_fine_case(time(8), time(20), time(10), time(23), timedelta(hours=9, minutes=30))
        self._test_fine_case(time(15), time(22), time(8), time(15), timedelta(0))
        self._test_fine_case(time(8), time(20), time(8, 3), time(20, 23), timedelta(hours=11))
        self._test_fine_case(time(8), time(20), time(8, 3), time(19, 23), timedelta(hours=10))
        self._test_fine_case(time(8), time(20), time(8, 50), time(19, 23), timedelta(hours=9, minutes=30))
        self._test_fine_case(time(8), time(20), time(8, 50), time(19, 37), timedelta(hours=10))

    def test_fine_calc_day_night(self):
        self.network.fines_settings = json.dumps(
           {
                r'.*': {
                    'arrive_step': 30,
                    'departure_step': 30,
                },
            }
        )
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.round_work_hours_alg = Network.ROUND_TO_HALF_AN_HOUR
        self.network.save()
        self.breaks.value='[[0, 3600, [60]]]'
        self.breaks.save()

        WorkerDay.objects.all().delete()
        dt = date.today()
        plan_wd = self._create_or_update_worker_day(
            self.cashier[2], 
            datetime.combine(dt, time(18)), 
            datetime.combine(dt + timedelta(1), time(1)), 
        )
        fact_wd = self._create_or_update_worker_day(
            self.cashier[2], 
            datetime.combine(dt, time(17, 50)), 
            datetime.combine(dt + timedelta(1), time(0, 7)), 
            is_fact=True,
            closest_plan_approved_id=plan_wd.id,
        )

        self.assertEqual(fact_wd.dttm_work_start_tabel, datetime.combine(dt, time(18)))
        self.assertEqual(fact_wd.dttm_work_end_tabel, datetime.combine(dt + timedelta(1), time(0)))
        work_hours, work_hours_day, work_hours_night = fact_wd.calc_day_and_night_work_hours()
        self.assertEqual(work_hours, 5)
        self.assertEqual(work_hours_day, 3.5)
        self.assertEqual(work_hours_night, 1.5)

    def test_fine_not_applied_because_of_allowed_interval(self):
        self.network.fines_settings = json.dumps(
           {
                r'.*': {
                    'arrive_step': 30,
                    'departure_step': 30,
                },
            }
        )
        self.network.only_fact_hours_that_in_approved_plan = True
        self.network.allowed_interval_for_late_arrival = timedelta(minutes=5)
        self.network.allowed_interval_for_early_departure = timedelta(minutes=5)
        self.network.save()

        fact_wd = self._test_fine_case(time(8), time(20), time(8, 4), time(19, 56), timedelta(hours=11, minutes=30))
        self.assertEqual(fact_wd.dttm_work_start_tabel, datetime.combine(fact_wd.dt, time(8)))
        self.assertEqual(fact_wd.dttm_work_end_tabel, datetime.combine(fact_wd.dt, time(20)))

        fact_wd = self._test_fine_case(time(8), time(20), time(8, 6), time(19, 53), timedelta(hours=10, minutes=30))
        self.assertEqual(fact_wd.dttm_work_start_tabel, datetime.combine(fact_wd.dt, time(8, 30)))
        self.assertEqual(fact_wd.dttm_work_end_tabel, datetime.combine(fact_wd.dt, time(19, 30)))
