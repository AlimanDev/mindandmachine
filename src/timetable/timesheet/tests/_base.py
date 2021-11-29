from datetime import datetime, time, date

import pandas as pd
from freezegun import freeze_time

from etc.scripts import fill_calendar
from src.base.tests.factories import (
    ShopFactory,
    UserFactory,
    GroupFactory,
    EmploymentFactory,
    NetworkFactory,
    EmployeeFactory,
    WorkerPositionFactory,
    BreakFactory,
)
from src.timetable.models import WorkerDay, WorkType, WorkTypeName
from src.timetable.tests.factories import WorkerDayFactory
from src.timetable.timesheet.tasks import calc_timesheets
from src.util.mixins.tests import TestsHelperMixin


class TestTimesheetMixin(TestsHelperMixin):
    @classmethod
    def setUpTestData(cls):
        cls.breaks = breaks = BreakFactory(value='[[0, 2040, [60]]]', code='1h')
        cls.network = NetworkFactory(breaks=breaks)
        cls.root_shop = ShopFactory(
            network=cls.network,
            settings__breaks=breaks,
        )
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
            settings__breaks=breaks,
        )
        cls.user_worker = UserFactory(email='worker@example.com', network=cls.network)
        cls.employee_worker = EmployeeFactory(user=cls.user_worker)
        cls.group_worker = GroupFactory(name='Сотрудник', network=cls.network)
        cls.position_worker = WorkerPositionFactory(
            name='Работник', group=cls.group_worker,
            breaks=breaks,
        )
        cls.employment_worker = EmploymentFactory(
            employee=cls.employee_worker, shop=cls.shop, position=cls.position_worker,
        )
        cls.work_type_name_worker = WorkTypeName.objects.create(
            position=cls.position_worker,
            network=cls.network,
            name='worker',
            code='worker',
        )
        cls.work_type_worker = WorkType.objects.create(
            work_type_name=cls.work_type_name_worker,
            shop=cls.shop,
        )

        for dt in pd.date_range(date(2021, 6, 7), date(2021, 6, 13)).date:
            WorkerDayFactory(
                is_approved=True,
                is_fact=True,
                shop=cls.shop,
                employment=cls.employment_worker,
                employee=cls.employee_worker,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(20)),
                cashbox_details__work_type=cls.work_type_worker,
            )
            WorkerDayFactory(
                is_approved=True,
                is_fact=False,
                shop=cls.shop,
                employment=cls.employment_worker,
                employee=cls.employee_worker,
                dt=dt,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(10)),
                dttm_work_end=datetime.combine(dt, time(20)),
                cashbox_details__work_type=cls.work_type_worker,
            )
        cls.add_group_perm(cls.group_worker, 'Timesheet', 'GET')
        cls.add_group_perm(cls.group_worker, 'Timesheet_stats', 'GET')
        fill_calendar.fill_days('2021.01.1', '2021.12.31', cls.shop.region.id)

    def _calc_timesheets(self, employee_id=None, dt_from=None, dt_to=None, dttm_now=None, reraise_exc=True):
        dttm_now = dttm_now or datetime.combine(date(2021, 6, 7), time(10, 10, 10))
        with freeze_time(dttm_now):
            calc_timesheets(employee_id__in=[employee_id or self.employee_worker.id], dt_from=dt_from, dt_to=dt_to, reraise_exc=reraise_exc)
