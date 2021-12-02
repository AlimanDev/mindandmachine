import json
from datetime import datetime

import pandas as pd
from django.contrib.contenttypes.models import ContentType
from faker.providers.date_time import Provider as DateTimeProvider

from src.base.models import Shop
from src.forecast.models import Receipt
from src.integration.models import ExternalSystem, GenericExternalCode
from .base import BaseImportStrategy


class BaseSystemImportStrategy(BaseImportStrategy):
    def __init__(self, settings_json, **kwargs):
        self.settings_dict = json.loads(settings_json)
        super(BaseSystemImportStrategy, self).__init__(**kwargs)


class ImportShopMappingStrategy(BaseSystemImportStrategy):
    def __init__(self, system_code, system_name, filename, file_format, wfm_shop_code_field_name,
                 wfm_shop_name_field_name, external_shop_code_field_name, **kwargs):
        self.system_code = system_code
        self.system_name = system_name
        self.filename = filename
        self.file_format = file_format
        self.wfm_shop_code_field_name = wfm_shop_code_field_name
        self.wfm_shop_name_field_name = wfm_shop_name_field_name
        self.external_shop_code_field_name = external_shop_code_field_name
        super(BaseSystemImportStrategy, self).__init__(**kwargs)

    def _read_file_to_df(self, f):
        if self.file_format == 'xlsx':
            return pd.read_excel(f)
        elif self.file_format == 'csv':
            return pd.read_csv(f)

        raise NotImplementedError

    def execute(self):
        errors = set()

        f = self.fs_engine.open_file(self.filename)
        try:
            df = self._read_file_to_df(f)
            lookup = {}
            if self.wfm_shop_code_field_name:
                lookup['code__in'] = list(df[self.wfm_shop_code_field_name].values)
                shops_dict = {s.code: s for s in Shop.objects.filter(**lookup)}
            elif self.wfm_shop_name_field_name:
                lookup['name__in'] = list(df[self.wfm_shop_name_field_name].values)
                shops_dict = {s.name: s for s in Shop.objects.filter(**lookup)}
            else:
                raise Exception('bad shop code/name settings')

            external_system, _created = ExternalSystem.objects.get_or_create(
                code=self.system_code, defaults={'name': self.system_name})

            for index, row in df.iterrows():
                shop_code = row[self.wfm_shop_code_field_name or self.wfm_shop_name_field_name]
                shop = shops_dict.get(shop_code)
                if not shop:
                    errors.add(f'no shop with code/name="{shop_code}"')
                    continue

                GenericExternalCode.objects.update_or_create(
                    external_system=external_system,
                    object_id=shop.id,
                    object_type=ContentType.objects.get_for_model(shop),
                    defaults=dict(
                        code=row[self.external_shop_code_field_name]
                    )
                )
        finally:
            f.close()
        return {'errors': list(errors)}


class ImportHistDataStrategy(BaseSystemImportStrategy):
    def __init__(self, system_code, data_type, separated_file_for_each_shop, filename_fmt, dt_from, dt_to,
                 shop_num_column_name, dt_or_dttm_column_name, dt_or_dttm_format, csv_delimiter, columns: list = None,
                 receipt_code_columns: list = None,
                 **kwargs):
        self._dt_provider = DateTimeProvider(generator=None)
        self.system_code = system_code
        self.data_type = data_type
        self.separated_file_for_each_shop = separated_file_for_each_shop
        self.filename_fmt = filename_fmt
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.csv_delimiter = csv_delimiter
        self.shop_num_column_name = shop_num_column_name
        self.dt_or_dttm_column_name = dt_or_dttm_column_name
        self.dt_or_dttm_format = dt_or_dttm_format
        self.columns = columns
        self.receipt_code_columns = receipt_code_columns
        self._init_cached_data()
        super(BaseSystemImportStrategy, self).__init__(**kwargs)

    def _init_cached_data(self):
        self.cached_data = {
            'generic_shop_ids': {g.code: g.object_id for g in
                                 GenericExternalCode.objects.filter(
                                     external_system__code=self.system_code,
                                     object_type=ContentType.objects.get_for_model(Shop),
                                 )},
        }

    def get_shop_id_by_shop_num(self, code):
        shop_id = self.cached_data['generic_shop_ids'].get(code)
        return shop_id

    def get_filename(self, dt, shop_code=None):
        kwargs = dict(
            data_type=self.data_type,
            year=dt.year,
            month=dt.month,
            day=dt.day,
        )
        if self.separated_file_for_each_shop:
            kwargs['shop_code'] = shop_code
        return self.filename_fmt.format(**kwargs)

    def get_dates_range(self):
        dt_from = self._dt_provider._parse_date(self.dt_from)
        dt_to = self._dt_provider._parse_date(self.dt_to)
        return list(pd.date_range(dt_from, dt_to).date)

    def get_dt_and_filename_pairs(self):
        dt_and_filename_pairs = []
        for dt in self.get_dates_range():
            if self.separated_file_for_each_shop:
                for shop_code in self.cached_data.get('generic_shop_ids').keys():
                    dt_and_filename_pairs.append((dt, self.get_filename(dt, shop_code=shop_code)))
            else:
                dt_and_filename_pairs.append((dt, self.get_filename(dt)))
        return dt_and_filename_pairs

    def execute(self):
        errors = set()
        res = {
            'errors': errors,
        }
        dt_and_filename_pairs = self.get_dt_and_filename_pairs()
        for dt, filename in dt_and_filename_pairs:
            load_errors = self.load_file(dt, filename)
            if load_errors:
                errors.union(load_errors)

        res['errors'] = list(res['errors'])
        return res

    def load_file(self, dt, filename):
        load_errors = set()
        f = self.fs_engine.open_file(filename)
        try:
            extra_kwargs = {}
            if self.columns:
                extra_kwargs['index_col'] = False
                extra_kwargs['names'] = self.columns
            df_chunks = pd.read_csv(f, dtype=str, delimiter=self.csv_delimiter, chunksize=1000, **extra_kwargs)

            for df in df_chunks:
                if self.receipt_code_columns:
                    df['receipt_code'] = df[self.receipt_code_columns].agg(''.join, axis=1)
                else:
                    df['receipt_code'] = df.apply(lambda x: hash(tuple(x)), axis=1)

                receipts = []
                receipt_codes = set()
                for index, row in df.iterrows():
                    shop_num = row[self.shop_num_column_name]
                    shop_id = self.get_shop_id_by_shop_num(shop_num)
                    if not shop_id:
                        load_errors.add(f'cant map shop_id for shop_num="{shop_num}"')
                        continue

                    dttm = datetime.strptime(
                        row[self.dt_or_dttm_column_name],
                        self.dt_or_dttm_format,
                    )
                    receipts.append(
                        Receipt(
                            code=row['receipt_code'],
                            dttm=dttm,
                            dt=dttm.date(),
                            shop_id=shop_id,
                            data_type=self.data_type,
                            info=row.to_json(),
                        )
                    )
                    receipt_codes.add(row['receipt_code'])
                Receipt.objects.filter(code__in=list(receipt_codes)).delete()
                Receipt.objects.bulk_create(receipts)
        finally:
            f.close()

        return load_errors
