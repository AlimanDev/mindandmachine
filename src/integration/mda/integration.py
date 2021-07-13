import logging
from datetime import timedelta

import pandas as pd
import requests
from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Q, F, Subquery, Exists, OuterRef, Case, When, Value, CharField, BooleanField, Max
from django.db.models.functions import Upper, Greatest
from django.utils import timezone

from src.base.models import (
    Shop,
    User,
    Employment,
)
from src.integration.models import VMdaUsers
from .serializers import (
    ShopDTOSerializer,
    RegionDTOSerializer,
    DivisionDTOSerializer,
    UserDTOSerializer,
)

CLOSED_OR_DELETED_THRESHOLD_DAYS = 180


class MdaIntegrationHelper:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger('mda_integration')
        self.dttm_now = timezone.now()
        self.dt_now = self.dttm_now.date()

    def _get_dttm_modified_q(self, threshold_seconds):
        return Q(dttm_modified__gt=self.dttm_now - timedelta(seconds=threshold_seconds))

    def _get_shops_queryset(self, threshold_seconds=None):
        qs = Shop.objects.filter(
            Q(employments__isnull=False),
            Q(dt_closed__isnull=True) | Q(dt_closed__gt=self.dt_now - timedelta(days=CLOSED_OR_DELETED_THRESHOLD_DAYS)),
            Q(dttm_deleted__isnull=True) | Q(
                dttm_deleted__gt=self.dt_now - timedelta(days=CLOSED_OR_DELETED_THRESHOLD_DAYS)),
            ~Q(code=''), code__isnull=False,
            level=3,
            latitude__isnull=False, longitude__isnull=False,
        ).annotate(
            directorLogin=Subquery(VMdaUsers.objects.filter(
                shop_code=OuterRef('code'),
                shop_name=OuterRef('name'),
                role='DIR',
                active=True,
            ).values_list('username', flat=True)[:1])
        ).distinct()
        if threshold_seconds:
            qs = qs.filter(self._get_dttm_modified_q(threshold_seconds))
        return qs

    def _get_regions_queryset(self, threshold_seconds=None):
        qs = Shop.objects.filter(
            Q(child__isnull=False) | Q(employments__isnull=False),
            Q(dttm_deleted__isnull=True) | Q(
                dttm_deleted__gt=self.dt_now - timedelta(days=CLOSED_OR_DELETED_THRESHOLD_DAYS)),
            ~Q(code=''), code__isnull=False,
            level=2,
            latitude__isnull=True, longitude__isnull=True,
        ).distinct()
        if threshold_seconds:
            qs = qs.filter(self._get_dttm_modified_q(threshold_seconds))
        return qs

    def _get_divisions_queryset(self, threshold_seconds=None):
        qs = Shop.objects.filter(
            Q(child__isnull=False) | Q(employments__isnull=False),
            Q(dttm_deleted__isnull=True) | Q(
                dttm_deleted__gt=self.dt_now - timedelta(days=CLOSED_OR_DELETED_THRESHOLD_DAYS)),
            ~Q(code=''), code__isnull=False,
            level=1,
            latitude__isnull=True, longitude__isnull=True,
        ).distinct()
        if threshold_seconds:
            qs = qs.filter(self._get_dttm_modified_q(threshold_seconds))
        return qs

    def _get_users_queryset(self, threshold_seconds=None):
        active_employments_qs = Employment.objects.get_active(
            dt_from=self.dt_now,
            dt_to=self.dt_now,
        )
        active_employments_subq = active_employments_qs.filter(employee__user_id=OuterRef('id'))
        qs = User.objects.annotate(
            upper_auth_type=Upper(F('auth_type')),
            active=Exists(active_employments_subq),
            position=Subquery(
                active_employments_subq.filter(position__isnull=False).order_by(
                    '-is_visible',
                    '-norm_work_hours',
                ).values_list('position__name', flat=True)[:1]
            ),
            level=Subquery(active_employments_subq.order_by('-shop__level').values_list('shop__level', flat=True)[:1]),
            orgLevel=Case(
                When(level=Value(0), then=Value('COMPANY', output_field=CharField())),
                When(level=Value(1), then=Value('DIVISION', output_field=CharField())),
                When(level=Value(2), then=Value('REGION', output_field=CharField())),
                When(level=Value(3), then=Value('SHOP', output_field=CharField())),
                default=Value('SHOP', output_field=CharField()), output_field=CharField(),
            ),
            orgUnits=Case(
                When(level=Value(0), then=None),
                default=ArrayAgg(
                    'employees__employments__shop', distinct=True,
                    filter=Q(
                        employees__employments__id__in=active_employments_qs.values_list('id', flat=True),
                        employees__employments__shop__level=F('level'),
                    ),
                ),
            ),
            admin=Exists(active_employments_subq.filter(
                Q(function_group__name__icontains='Администратор') |
                Q(position__group__name__icontains='Администратор')
            )),
            shopDirector=Exists(VMdaUsers.objects.filter(
                id=OuterRef('id'),
                role='DIR',
                active=True,
            )),
            supervisor=Value(True, output_field=BooleanField()),
            _levelGtShopExists=Exists(active_employments_subq.filter(shop__level__lt=3)),
            _shopLevelExitst=Exists(active_employments_subq.filter(shop__level__gte=3)),
            userChecklistsOrganizer=Case(
                When(_shopLevelExitst=Value(True), then=Value(False, output_field=BooleanField())),
                When(_levelGtShopExists=Value(True), then=Value(True, output_field=BooleanField())),
                default=Value(False, output_field=BooleanField()), output_field=BooleanField(),
            ),
            surveyAdmin=F('admin'),
            timeZoneId=Subquery(
                active_employments_subq.order_by(
                    '-is_visible',
                    '-norm_work_hours',
                ).values_list('shop__timezone', flat=True)[:1]
            ),
            mda_lang=Case(
                When(lang='ru', then=Value('ru_RU', output_field=CharField())),
                When(lang='en', then=Value('en_EN', output_field=CharField())),
            ),
            user_last_modified=Max('dttm_modified'),
            employment_last_modified=Subquery(
                active_employments_subq.order_by('-dttm_modified').values_list('dttm_modified', flat=True)[:1]),
            position_last_modified=Subquery(
                active_employments_subq.order_by(
                    '-position__dttm_modified'
                ).values_list('position__dttm_modified', flat=True)[:1]),
            last_dttm_modified=Greatest(
                F('user_last_modified'),
                F('employment_last_modified'),
                F('position_last_modified'),
            ),
            add_to_unload=Exists(Employment.objects.get_active(
                dt_from=self.dt_now - timedelta(days=60), dt_to=self.dt_now,
                employee__user_id=OuterRef('id'),
            ))
        ).filter(
            add_to_unload=True,
        )
        if threshold_seconds:
            qs = qs.filter(
                Q(last_dttm_modified__gt=self.dttm_now - timedelta(seconds=threshold_seconds)),
            )
        return qs

    def _get_orgstruct_data(self, threshold_seconds=None):
        return {
            'divisions': DivisionDTOSerializer(self._get_divisions_queryset(threshold_seconds), many=True).data,
            'regions': RegionDTOSerializer(self._get_regions_queryset(threshold_seconds), many=True).data,
            'shops': ShopDTOSerializer(self._get_shops_queryset(threshold_seconds), many=True).data,
        }

    def _get_users_data(self, threshold_seconds=None):
        return UserDTOSerializer(self._get_users_queryset(threshold_seconds), many=True).data

    def export_data(self, threshold_seconds=None, plain_shops=False, export_path=None, output=None):
        assert (export_path or output) and not (export_path and output)
        """
        from src.integration.mda.integration import MdaIntegrationHelper
        MdaIntegrationHelper().export_data(export_path='orgstruct.xlsx', plain_shops=True)
        """
        data = self._get_orgstruct_data(threshold_seconds=threshold_seconds)
        divisions_df = pd.DataFrame(data['divisions'])
        regions_df = pd.DataFrame(data['regions'])

        if plain_shops:
            divisions_dict = {d['id']: d for d in data['divisions']}
            regions_dict = {d['id']: d for d in data['regions']}
            for shop_data in data['shops']:
                region_data = regions_dict[shop_data['regionId']]
                division_data = divisions_dict[region_data['divisionId']]
                shop_data['regionName'] = region_data['name']
                shop_data['divisionName'] = division_data['name']
        shops_df = pd.DataFrame(data['shops'])
        users_df = pd.DataFrame(self._get_users_data(threshold_seconds=threshold_seconds))

        writer = pd.ExcelWriter(export_path or output, engine='xlsxwriter')

        divisions_df.to_excel(writer, sheet_name='Дивизионы')
        regions_df.to_excel(writer, sheet_name='Регионы')
        shops_df.to_excel(writer, sheet_name='Магазины')
        users_df.to_excel(writer, sheet_name='Пользователи')

        writer.save()

    def sync_orgstruct(self, threshold_seconds=settings.MDA_SYNC_DEPARTMENTS_THRESHOLD_SECONDS):
        resp = requests.post(
            url=settings.MDA_PUBLIC_API_HOST + '/api/public/v1/mindandmachine/loadOrgstruct',
            json=self._get_orgstruct_data(threshold_seconds=threshold_seconds),
            headers={
                'x-public-token': settings.MDA_PUBLIC_API_AUTH_TOKEN,
            },
            timeout=(5, 30),
        )
        # TODO: запись ошибок в лог
        try:
            resp.raise_for_status()
        except requests.RequestException:
            self.logger.exception(f'text:{resp.text}, headers: {resp.headers}')

    def sync_users(self, threshold_seconds=settings.MDA_SYNC_DEPARTMENTS_THRESHOLD_SECONDS):
        resp = requests.post(
            url=settings.MDA_PUBLIC_API_HOST + '/api/public/v1/mindandmachine/loadUsers',
            json=self._get_users_data(threshold_seconds=threshold_seconds),
            headers={
                'x-public-token': settings.MDA_PUBLIC_API_AUTH_TOKEN,
            },
            timeout=(5, 30),
        )
        # TODO: запись ошибок в лог
        try:
            resp.raise_for_status()
        except requests.RequestException:
            self.logger.exception(f'text:{resp.text}, headers: {resp.headers}')
