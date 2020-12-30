import json
import random
from calendar import Calendar
from datetime import datetime, timedelta, time

from django.urls import reverse

from src.base.models import Employment, FunctionGroup
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails
from src.util.test import create_departments_and_users
from src.util.utils import generate_user_token


class TestsHelperMixin:
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def _set_authorization_token(self, login):
        response = self.client.post(
            path=reverse('time_attendance_auth'),
            data=json.dumps({
                'username': login,
                'token': generate_user_token(login),
            }),
            content_type='application/json'
        )

        token = response.json()['token']
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Token %s' % token

    @classmethod
    def create_departments_and_users(cls):
        create_departments_and_users(cls)

    @staticmethod
    def get_url(view_name, **kwargs: dict):
        return reverse(view_name, kwargs=kwargs)

    def print_resp(self, resp):
        try:
            resp_data = resp.json()
            print(json.dumps(resp_data, indent=4, ensure_ascii=False))
        except TypeError:
            print(resp.content)

    @staticmethod
    def dump_data(data):
        return json.dumps(data)

    @classmethod
    def _generate_plan_and_fact_worker_days_for_shop_employments(cls, shop, work_type, dt_from, dt_to):
        assert dt_from.year == dt_to.year and dt_from.month == dt_to.month

        year = dt_from.year
        month = dt_from.month

        active_shop_empls = Employment.objects.get_active(
            network_id=shop.network_id, dt_from=dt_from, dt_to=dt_to, shop=shop)
        plan_start_time = time(hour=10, minute=0)
        plan_end_time = time(hour=20, minute=0)

        calendar = Calendar()

        for empl in active_shop_empls:
            for day in calendar.itermonthdates(year, month):
                is_workday = day.weekday() not in [5, 6]
                kwargs = dict(
                    dt=day,
                    type='W' if is_workday else 'H',
                    is_fact=False,
                    is_approved=True,
                    worker_id=empl.user_id,
                    employment_id=empl.id,
                )
                if is_workday:
                    kwargs['shop_id'] = shop.id
                    kwargs['dttm_work_start'] = datetime.combine(day, plan_start_time)
                    kwargs['dttm_work_end'] = datetime.combine(day, plan_end_time)

                wd = WorkerDay.objects.create(**kwargs)
                WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    work_type=work_type,
                )

                if is_workday:
                    is_absenteeism = random.randint(1, 100) < 10  # прогул
                    if not is_absenteeism:
                        signs = [1, -1]
                        start_delta_sign = random.choice(signs)
                        end_delta_sign = random.choice(signs)
                        start_minutes = random.randrange(0, 90) * start_delta_sign
                        end_minutes = random.randrange(0, 90) * end_delta_sign
                        kwargs['is_fact'] = True
                        kwargs['dttm_work_start'] = datetime.combine(
                            day, plan_start_time) + timedelta(minutes=start_minutes)
                        kwargs['dttm_work_end'] = datetime.combine(day, plan_end_time) + timedelta(minutes=end_minutes)
                        WorkerDay.objects.create(**kwargs)

    def clean_cached_props(self, cached_props=None):
        cached_props = cached_props or (
            ('root_shop', ['open_times', 'close_times']),
            ('reg_shop1', ['open_times', 'close_times']),
            ('reg_shop2', ['open_times', 'close_times']),
            ('shop', ['open_times', 'close_times']),
            ('shop2', ['open_times', 'close_times']),
            ('shop3', ['open_times', 'close_times']),
        )
        for attr, props in cached_props:
            if hasattr(self, attr):
                for prop in props:
                    try:
                        obj = getattr(self, attr)
                        del obj.__dict__[prop]
                    except (KeyError, AttributeError):
                        pass

    @staticmethod
    def add_group_perm(group, perm_name, perm_method):
        FunctionGroup.objects.create(
            group=group,
            method=perm_method,
            func=perm_name,
            level_up=1,
            level_down=99,
        )
