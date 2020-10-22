import json
from calendar import Calendar
from django.urls import reverse
from src.timetable.models import WorkerDay
from src.util.test import create_departments_and_users
from datetime import datetime, timedelta, time, date
from src.base.models import Employment
import random

class TestsHelperMixin:
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def create_departments_and_users(cls):
        create_departments_and_users(cls)

    @staticmethod
    def get_url(view_name, **kwargs: dict):
        return reverse(view_name, kwargs=kwargs)

    def print_resp(self, resp):
        print(json.dumps(resp.json(), indent=4, ensure_ascii=False))

    @staticmethod
    def dump_data(data):
        return json.dumps(data)

    @classmethod
    def _generate_plan_and_fact_worker_days_for_shop_employments(cls, shop, dt_from, dt_to):
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

                WorkerDay.objects.create(**kwargs)

                if is_workday:
                    is_absenteeism = random.randint(1, 100) == 1  # прогул
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
