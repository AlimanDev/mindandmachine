import json
import random
from calendar import Calendar
from datetime import datetime, timedelta, time
from unittest import mock

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.urls import reverse

from src.base.models import Employment, FunctionGroup
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkerDayType
from src.timetable.tests.factories import WorkerDayTypeFactory, WorkerDayFactory
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
    def get_url(view_name, *args, **kwargs: dict):
        return reverse(view_name, args=args, kwargs=kwargs)

    def pp_data(self, d):
        print(json.dumps(d, indent=4, ensure_ascii=False))

    def print_resp(self, resp):
        try:
            resp_data = resp.json()
            print(json.dumps(resp_data, indent=4, ensure_ascii=False))
        except TypeError:
            print(resp.content)

    @staticmethod
    def dump_data(data):
        return json.dumps(data, cls=DjangoJSONEncoder)

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
                    type_id='W' if is_workday else 'H',
                    is_fact=False,
                    is_approved=True,
                    employee_id=empl.employee_id,
                    employment_id=empl.id,
                )
                if is_workday:
                    kwargs['shop_id'] = shop.id
                    kwargs['dttm_work_start'] = datetime.combine(day, plan_start_time)
                    kwargs['dttm_work_end'] = datetime.combine(day, plan_end_time)
                wd, _wd_created = WorkerDay.objects.get_or_create(
                    dt=day,
                    is_fact=False,
                    is_approved=True,
                    employee_id=empl.employee_id,
                    defaults=kwargs
                )
                if _wd_created:
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
                            kwargs['dttm_work_end'] = datetime.combine(day, plan_end_time) + timedelta(
                                minutes=end_minutes)
                            wd = WorkerDay.objects.create(**kwargs)
                            WorkerDayCashboxDetails.objects.create(
                                worker_day=wd,
                                work_type=work_type,
                            )
                else:
                    change_empl = random.randint(0, 1) == 1
                    if change_empl:
                        wd.employment = empl
                        wd.save()
                        fact = WorkerDay.objects.filter(employee_id=wd.employee_id, dt=wd.dt, is_fact=True,
                                                        is_approved=True).first()
                        change_fact = random.randint(0, 100) < 90
                        if change_fact and fact:
                            fact.employment = empl
                            fact.save()

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

    @staticmethod
    def _add_network_settings_value(network, key, value):
        network_settings = json.loads(network.settings_values)
        network_settings[key] = value
        network.settings_values = json.dumps(network_settings)

    def _change_wd_data(self, wd_id, data_to_change, auth_user=None):
        self.client.force_authenticate(user=auth_user or self.user1)
        resp = self.client.get(self.get_url('WorkerDay-detail', pk=wd_id))
        wd_data = resp.json()
        wd_data.update(data_to_change)
        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            resp = self.client.put(
                self.get_url('WorkerDay-detail', pk=wd_id),
                data=self.dump_data(wd_data),
                content_type='application/json',
            )
        return resp

    def _approve(self, shop_id, is_fact, dt_from, dt_to, wd_types=None, employee_ids=None):
        approve_data = {
            'shop_id': shop_id,
            'is_fact': is_fact,
            'dt_from': dt_from,
            'dt_to': dt_to,
        }
        if wd_types:
            approve_data['wd_types'] = wd_types
        if employee_ids:
            approve_data['employee_ids'] = employee_ids

        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            resp = self.client.post(
                self.get_url('WorkerDay-approve'), data=self.dump_data(approve_data), content_type='application/json')
        return resp

    def _create_san_day(self):
        return WorkerDayTypeFactory(
            code='SD',
            name='Санитарный день',
            short_name='САН',
            html_color='white',
            use_in_plan=True,
            use_in_fact=True,
            excel_load_code='СД',
            is_dayoff=False,
            is_work_hours=False,
            is_reduce_norm=False,
            show_stat_in_hours=True,
            show_stat_in_days=True,
        )

    @property
    def wd_types_dict(self):
        return WorkerDayType.get_wd_types_dict()

    def _create_worker_day(self, employment, dttm_work_start, dttm_work_end, is_fact=False, is_approved=True,
                           shop_id=None):
        return WorkerDayFactory(
            is_approved=is_approved,
            is_fact=is_fact,
            shop_id=shop_id or employment.shop_id,
            employment=employment,
            employee_id=employment.employee_id,
            dt=dttm_work_start.date(),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
        )
