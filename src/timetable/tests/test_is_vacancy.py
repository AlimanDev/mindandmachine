from copy import deepcopy
from datetime import date, datetime, time, timedelta
from src.base.tests.factories import EmployeeFactory, EmploymentFactory, GroupFactory, NetworkFactory, ShopFactory, UserFactory
from src.timetable.models import AttendanceRecords, GroupWorkerDayPermission, WorkerDay, WorkerDayCashboxDetails, WorkerDayPermission
from src.timetable.tests.factories import WorkTypeFactory, WorkerDayFactory
from src.timetable.worker_day.utils import copy_as_excel_cells, create_worker_days_range, exchange
from src.util.mixins.tests import TestsHelperMixin
from rest_framework.test import APITestCase

class TestIsVacancySetting(TestsHelperMixin, APITestCase):
    
    @classmethod
    def setUpTestData(cls) -> None:
        cls.network = NetworkFactory()
        cls.shop = ShopFactory(network=cls.network)
        cls.shop2 = ShopFactory(network=cls.network)
        cls.worker_group = GroupFactory(network=cls.network)
        cls.worker_group.subordinates.add(cls.worker_group)
        cls.user_worker = UserFactory(network=cls.network)
        cls.user_worker2 = UserFactory(network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.employee_worker2 = EmployeeFactory(user=cls.user_worker2)

        cls.main_work_type = WorkTypeFactory(
            work_type_name__name='Основной',
            shop=cls.shop,
        )
        cls.additional_work_type = WorkTypeFactory(
            work_type_name__name='Доп',
            shop=cls.shop,
        )

        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker,
            shop=cls.shop,
            work_types__work_type=cls.main_work_type,
            work_types__priority=1,
            function_group=cls.worker_group,
        )
        cls.employment_worker2 = EmploymentFactory(
            employee=cls.employee_worker2,
            shop=cls.shop,
            work_types__work_type=cls.additional_work_type,
            work_types__priority=1,
            function_group=cls.worker_group,
        )
        
        cls.shop2_work_type = WorkTypeFactory(
            work_type_name__name='Основной',
            shop=cls.shop2,
        )
        cls.dt_now = date.today()
        cls.plan_worker_day = WorkerDayFactory(
            employee=cls.employee_worker,
            employment=cls.employment_worker,
            cashbox_details__work_type=cls.main_work_type,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=cls.dt_now,
            dttm_work_start=datetime.combine(cls.dt_now, time(8)),
            dttm_work_end=datetime.combine(cls.dt_now, time(15)),
            shop=cls.shop,
            is_fact=False,
            is_approved=True,
        )
        GroupWorkerDayPermission.objects.bulk_create(
            GroupWorkerDayPermission(
                group=cls.worker_group,
                worker_day_permission=wdp,
            ) for wdp in WorkerDayPermission.objects.all()
        )
        cls.add_group_perm(cls.worker_group, 'WorkerDay', 'POST')
        cls.add_group_perm(cls.worker_group, 'WorkerDay', 'PUT')
        cls.add_group_perm(cls.worker_group, 'WorkerDay_batch_update_or_create', 'POST')

    def setUp(self):
        self.client.force_authenticate(self.user_worker)

    def test_is_vacancy_with_attendance_records_creation(self):
        # not setted
        record = AttendanceRecords.objects.create(
            user=self.user_worker,
            employee=self.employee_worker,
            shop=self.shop,
            dt=self.dt_now,
            dttm=datetime.combine(self.dt_now, time(8, 10)),
        )
        self.assertFalse(record.fact_wd.is_vacancy)

        # setted because of shop
        record.fact_wd.delete()
        self.plan_worker_day.shop = self.shop2
        self.plan_worker_day.save()

        record.shop = self.shop2
        record.save()
        self.assertTrue(record.fact_wd.is_vacancy)

        # setted because of work_type
        record.fact_wd.delete()
        self.plan_worker_day.shop = self.shop
        self.plan_worker_day.save()

        WorkerDayCashboxDetails.objects.filter(worker_day=self.plan_worker_day).update(work_type=self.additional_work_type)
        record.shop = self.shop
        record.save()

        self.assertTrue(record.fact_wd.is_vacancy)

    def test_is_vacancy_on_worker_day_create(self):
        worker_day_data_init = {
            'employee_id': self.employee_worker.id,
            'employment_id': self.employment_worker.id,
            'shop_id': self.shop.id,
            'dt': self.dt_now,
            'dttm_work_start': datetime.combine(self.dt_now, time(8)),
            'dttm_work_end': datetime.combine(self.dt_now, time(20)),
            'is_fact': False,
            'type': WorkerDay.TYPE_WORKDAY,
            'worker_day_details': [
                {
                    'work_type_id': self.main_work_type.id,
                    'work_part': 1.0,
                }
            ]
        }
        worker_day_data = deepcopy(worker_day_data_init)

        # not setted
        response = self.client.post(
            self.get_url('WorkerDay-list'),
            data=self.dump_data(worker_day_data),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)

        worker_day = WorkerDay.objects.get(id=response.json()['id'])

        self.assertFalse(worker_day.is_vacancy)

        # setted because of shop
        worker_day_data['shop_id'] = self.shop2.id
        worker_day_data['worker_day_details'][0]['work_type_id'] = self.shop2_work_type.id

        response = self.client.put(
            self.get_url('WorkerDay-detail', pk=worker_day.id),
            data=self.dump_data(worker_day_data),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        worker_day.refresh_from_db()
        self.assertTrue(worker_day.is_vacancy)

        worker_day.is_vacancy = False
        worker_day.save()

        # setted because of work type

        worker_day_data = deepcopy(worker_day_data_init)
        worker_day_data['worker_day_details'][0]['work_type_id'] = self.additional_work_type.id

        response = self.client.put(
            self.get_url('WorkerDay-detail', pk=worker_day.id),
            data=self.dump_data(worker_day_data),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        worker_day.refresh_from_db()
        self.assertTrue(worker_day.is_vacancy)
        worker_day.delete()

        # batch
        options = {
            'return_response': True,
        }
        worker_day_data = deepcopy(worker_day_data_init)

        response = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'),
            data=self.dump_data(
                {
                    'data': [worker_day_data],
                    'options': options,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)

        worker_day = WorkerDay.objects.get(id=response.json()['data'][0]['id'])

        self.assertFalse(worker_day.is_vacancy)

        worker_day_data['id'] = worker_day.id
        worker_day_data['shop_id'] = self.shop2.id
        worker_day_data['worker_day_details'][0]['work_type_id'] = self.shop2_work_type.id

        response = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'),
            data=self.dump_data(
                {
                    'data': [worker_day_data],
                    'options': options,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        worker_day.refresh_from_db()
        self.assertTrue(worker_day.is_vacancy)
        worker_day.is_vacancy = False
        worker_day.save()

        worker_day_data['shop_id'] = self.shop.id
        worker_day_data['worker_day_details'][0]['work_type_id'] = self.additional_work_type.id

        response = self.client.post(
            self.get_url('WorkerDay-batch-update-or-create'),
            data=self.dump_data(
                {
                    'data': [worker_day_data],
                    'options': options,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        worker_day.refresh_from_db()
        self.assertTrue(worker_day.is_vacancy)

    def test_is_vacancy_with_copy_as_excel_cells(self):
        created_wds, _ = copy_as_excel_cells(
            self.employee_worker.id,
            [self.dt_now],
            self.employee_worker2.id,
            [self.dt_now],
            is_approved=True,
            user=self.user_worker,
        )
        worker_day = WorkerDay.objects.get(id=created_wds[0].id)
        self.assertTrue(worker_day.is_vacancy)

    def test_is_vacancy_on_exchange(self):
        WorkerDayFactory(
            employee=self.employee_worker2,
            employment=self.employment_worker2,
            cashbox_details__work_type=self.additional_work_type,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.dt_now,
            dttm_work_start=datetime.combine(self.dt_now, time(8)),
            dttm_work_end=datetime.combine(self.dt_now, time(15)),
            shop=self.shop,
            is_fact=False,
            is_approved=True,
        )

        created_wdays = exchange(
            {
                'user': self.user_worker,
                'is_approved': True,
                'employee1_id': self.employee_worker.id,
                'employee2_id': self.employee_worker2.id,
                'dates': [self.dt_now],
            },
            {},
        )

        self.assertEqual(len(created_wdays), 2)
        self.assertEqual(WorkerDay.objects.filter(id__in=map(lambda x: x.id, created_wdays), is_vacancy=True).count(), 2)

    def test_is_vacancy_on_create_worker_days_range(self):
        create_kwargs = dict(
            shop_id=self.shop2.id, 
            employee_id=self.employee_worker.id, 
            tm_work_start=time(8), 
            tm_work_end=time(10), 
            cashbox_details=[
                {
                    'work_type_id': self.shop2_work_type.id,
                    'work_part': 1.0,
                }
            ],
            created_by=self.user_worker,
        )
        # by shop
        created_wdays = create_worker_days_range(
            [self.dt_now], 
            **create_kwargs,
        )
        worker_day = WorkerDay.objects.get(id=created_wdays[0].id)
        self.assertTrue(worker_day.is_vacancy)
        worker_day.delete()
        create_kwargs['shop_id'] = self.shop.id
        create_kwargs['cashbox_details'][0]['work_type_id'] = self.additional_work_type.id
        created_wdays = create_worker_days_range(
            [self.dt_now], 
            **create_kwargs,
        )
        worker_day = WorkerDay.objects.get(id=created_wdays[0].id)
        self.assertTrue(worker_day.is_vacancy)

        created_wdays = create_worker_days_range(
            [self.dt_now + timedelta(1)], 
            type_id=WorkerDay.TYPE_HOLIDAY,
            employee_id=self.employee_worker.id,
            created_by=self.user_worker,
        )
        worker_day = WorkerDay.objects.get(id=created_wdays[0].id)
        self.assertFalse(worker_day.is_vacancy)
