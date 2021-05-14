import logging
from datetime import timedelta

import pandas as pd
import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from src.base.models import (
    Shop,
)
from .serializers import (
    ShopDTOSerializer,
    RegionDTOSerializer,
    DivisionDTOSerializer,
)


class MdaIntegrationHelper:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger('django.request')
        self.dttm_now = timezone.now()
        self.dt_now = self.dttm_now.date()

    def _get_dttm_modified_q(self, threshold_seconds):
        return Q(dttm_modified__gt=self.dttm_now - timedelta(seconds=threshold_seconds))

    def _get_shops_queryset(self, threshold_seconds=None):
        qs = Shop.objects.filter(
            Q(employments__isnull=False),
            Q(dt_closed__isnull=True) | Q(dt_closed__gt=self.dt_now - timedelta(days=180)),
            Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gt=self.dttm_now - timedelta(days=180)),
            ~Q(code=''), code__isnull=False,
            level=3,
            latitude__isnull=False, longitude__isnull=False,
        ).distinct()
        if threshold_seconds:
            qs = qs.filter(self._get_dttm_modified_q(threshold_seconds))
        return qs

    def _get_regions_queryset(self, threshold_seconds=None):
        qs = Shop.objects.filter(
            Q(child__isnull=False) | Q(employments__isnull=False),
            Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gt=self.dttm_now - timedelta(days=180)),
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
            Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gt=self.dttm_now - timedelta(days=180)),
            ~Q(code=''), code__isnull=False,
            level=1,
            latitude__isnull=True, longitude__isnull=True,
        ).distinct()
        if threshold_seconds:
            qs = qs.filter(self._get_dttm_modified_q(threshold_seconds))
        return qs

    def _get_data(self, threshold_seconds=None):
        return {
            'divisions': DivisionDTOSerializer(self._get_divisions_queryset(threshold_seconds), many=True).data,
            'regions': RegionDTOSerializer(self._get_regions_queryset(threshold_seconds), many=True).data,
            'shops': ShopDTOSerializer(self._get_shops_queryset(threshold_seconds), many=True).data,
        }

    def export_data(self, export_path, threshold_seconds=None, plain_shops=False):
        """
        from src.integration.mda.integration import MdaIntegrationHelper
        MdaIntegrationHelper().export_data(export_path='orgstruct.xlsx', plain_shops=True)
        """
        data = self._get_data(threshold_seconds=threshold_seconds)
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

        writer = pd.ExcelWriter(export_path, engine='xlsxwriter')

        divisions_df.to_excel(writer, sheet_name='Дивизионы')
        regions_df.to_excel(writer, sheet_name='Регионы')
        shops_df.to_excel(writer, sheet_name='Магазины')

        writer.save()

    def sync_mda_data(self, threshold_seconds=settings.MDA_SYNC_DEPARTMENTS_THRESHOLD_SECONDS):
        resp = requests.post(
            url=settings.MDA_PUBLIC_API_HOST + '/api/public/v1/mindandmachine/loadOrgstruct',
            json=self._get_data(threshold_seconds=threshold_seconds),
            headers={
                'x-public-token': settings.MDA_PUBLIC_API_AUTH_TOKEN,
            },
            timeout=(5, 30),
        )
        try:
            resp.raise_for_status()
        except requests.RequestException:
            self.logger.exception(f'text:{resp.text}, headers: {resp.headers}')
