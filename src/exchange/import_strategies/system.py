import json
from datetime import datetime, time

import pandas as pd
from django.contrib.contenttypes.models import ContentType
from django.utils.functional import cached_property
from faker.providers.date_time import Provider as DateTimeProvider

from src.base.models import Shop
from src.exchange.models import SystemImportStrategy
from src.forecast.models import Receipt
from src.integration.models import ExternalSystem, GenericExternalCode
from .base import BaseImportStrategy


class BaseSystemImportStrategy(BaseImportStrategy):
    def __init__(self, settings_json, **kwargs):
        self.settings_dict = json.loads(settings_json)
        super(BaseSystemImportStrategy, self).__init__(**kwargs)


class PobedaImportShopMapping(BaseSystemImportStrategy):
    def execute(self):
        results = {}

        filename = self.settings_dict.get('filename')
        f = self.fs_engine.open_file(filename)
        try:
            df = pd.read_excel(f, engine='xlrd')
            shop_code_1s_field_name = self.settings_dict.get('shop_code_1s_field_name', 'GUID в 1С')
            shop_number_run_field_name = self.settings_dict.get('shop_number_run_field_name', 'Код магазина')
            shops_dict = {s.code: s for s in Shop.objects.filter(code__in=list(df[shop_code_1s_field_name].values))}

            pobeda_external_system, _created = ExternalSystem.objects.get_or_create(
                code='pobeda', defaults={'name': 'Победа'})

            for index, row in df.iterrows():
                shop_code = row[shop_code_1s_field_name]
                shop = shops_dict.get(shop_code)
                if not shop:
                    results.setdefault('errors', []).append(f'no shop with code="{shop_code}"')
                    continue

                GenericExternalCode.objects.update_or_create(
                    external_system=pobeda_external_system,
                    object_id=shop.id,
                    object_type=ContentType.objects.get_for_model(shop),
                    defaults=dict(
                        code=row[shop_number_run_field_name]
                    )
                )
        finally:
            f.close()
        return results


class PobedaImport(BaseSystemImportStrategy):
    data_type = None

    def __init__(self, **kwargs):
        self.dt_provider = DateTimeProvider(generator=None)
        self._init_cached_data()
        super(PobedaImport, self).__init__(**kwargs)

    def _init_cached_data(self):
        self.cached_data = {
            # 'native_shops': {s.id: s for s in Shop.objects.all()},
            'generic_shop_ids': {g.code: g.object_id for g in
                                 GenericExternalCode.objects.filter(
                                     external_system__code='pobeda',
                                     object_type=ContentType.objects.get_for_model(Shop),
                                 )},
        }

    @cached_property
    def filename_fmt(self):
        return self.data_type + '_{year:04d}{month:02d}{day:02d}.csv'

    def get_shop_id_by_shop_num(self, code):
        shop_id = self.cached_data['generic_shop_ids'].get(code)
        # shop = self.cached_data['native_shops'].get(shop_id)
        return shop_id

    def get_filename(self, dt):
        return self.filename_fmt.format(
            year=dt.year,
            month=dt.month,
            day=dt.day,
        )

    def get_dates_range(self):
        dt_from = self.dt_provider._parse_date(self.settings_dict.get('dt_from', 'today'))
        dt_to = self.dt_provider._parse_date(self.settings_dict.get('dt_to', 'today'))
        return list(pd.date_range(dt_from, dt_to).date)

    def get_dt_and_filename_pairs(self):
        dt_and_filename_pairs = []
        for dt in self.get_dates_range():
            dt_and_filename_pairs.append((dt, self.get_filename(dt)))
        return dt_and_filename_pairs

    def load_file(self, dt, filename):
        raise NotImplementedError

    def execute(self):
        errors = []
        res = {
            'errors': errors,
        }
        dt_and_filename_pairs = self.get_dt_and_filename_pairs()
        for dt, filename in dt_and_filename_pairs:
            load_errors = self.load_file(dt, filename)
            if load_errors:
                errors.extend(load_errors)

        return res


class PobedaImportPurchases(PobedaImport):
    data_type = 'purchases'

    def load_file(self, dt, filename):
        load_errors = []
        f = self.fs_engine.open_file(filename)
        try:
            df = pd.read_csv(f, dtype=str, delimiter=';', names=[
                'Номер магазина id',
                'Номер кассы id',
                'Номер чека',
                'Дата время открытия чека',
                'Дата время закрытия чека',
                'Табель кассира (сотрудника) id',
                'Id SKU',
                'Количество товара: суммарно по 1 SKU либо 1 единицы SKU',
                'Единица измерения',
                'Стоимость SKU: суммарно по 1 SKU либо 1 единицы SKU',
                'Способ оплаты: нал/безнал',
                'Наличие бонусной карты',
            ])
            df['receipt_code'] = df.apply(lambda x: hash(tuple(x)), axis=1)
            for shop_num, grouped_df in df.groupby('Номер магазина id'):
                shop_id = self.get_shop_id_by_shop_num(shop_num)
                if not shop_id:
                    load_errors.append(f'cant map shop_id for shop_num="{shop_num}"')
                    continue
                receipt_objs = []
                Receipt.objects.filter(shop_id=shop_id, data_type=self.data_type, dt=dt).delete()
                for index, row in grouped_df.iterrows():
                    dttm = datetime.strptime(
                        row['Дата время открытия чека'],
                        self.settings_dict.get('dttm_format', '%d.%m.%Y %H:%M:%S'),
                    )
                    receipt_objs.append(
                        Receipt(
                            code=row['receipt_code'],
                            dttm=dttm,
                            dt=dttm.date(),
                            shop_id=shop_id,
                            data_type='purchases',
                            info=row.to_json(),
                        )
                    )
                if receipt_objs:
                    Receipt.objects.bulk_create(receipt_objs, batch_size=10000)
        finally:
            f.close()

        return load_errors


class PobedaImportBrak(PobedaImport):
    data_type = 'brak'

    def load_file(self, dt, filename):
        load_errors = []
        f = self.fs_engine.open_file(filename)
        try:
            df = pd.read_csv(f, dtype=str, delimiter=';', index_col=False, names=[
                'Какой-то guid',
                'Номер магазина id',
                'Дата',
                'Тип списания',
                'Id SKU',
                'Количество товара',
            ])
            df['receipt_code'] = df['Какой-то guid'] + df['Id SKU']  # TODO: какой код?
            for shop_num, grouped_df in df.groupby('Номер магазина id'):
                shop_id = self.get_shop_id_by_shop_num(shop_num)
                if not shop_id:
                    load_errors.append(f'cant map shop_id for shop_num="{shop_num}"')
                    continue
                for index, row in grouped_df.iterrows():
                    dt = datetime.strptime(
                        row['Дата'],
                        self.settings_dict.get('dt_format', '%d.%m.%Y'),
                    )
                    Receipt.objects.update_or_create(  # TODO: batch_update_or_create ?
                        code=row['receipt_code'],
                        defaults=dict(
                            dttm=datetime.combine(dt, time(minute=1)),
                            dt=dt,
                            shop_id=shop_id,
                            data_type=self.data_type,
                            info=row.to_json(),
                        )
                    )
        finally:
            f.close()

        return load_errors


class PobedaImportDelivery(PobedaImport):
    data_type = 'delivery'

    def load_file(self, dt, filename):
        load_errors = []
        f = self.fs_engine.open_file(filename)
        try:
            df = pd.read_csv(f, dtype=str, delimiter=';', index_col=False, names=[
                'Какой-то guid',
                'Номер магазина id',
                'Дата и время',
                'Тип поставки',
                'Id SKU',
                'Количество товара',
            ])
            df['receipt_code'] = df['Какой-то guid'] + df['Id SKU']  # TODO: какой код?
            for shop_num, grouped_df in df.groupby('Номер магазина id'):
                shop_id = self.get_shop_id_by_shop_num(shop_num)
                if not shop_id:
                    load_errors.append(f'cant map shop_id for shop_num="{shop_num}"')
                    continue
                for index, row in grouped_df.iterrows():
                    dttm = datetime.strptime(
                        row['Дата и время'],
                        self.settings_dict.get('dttm_format', '%d.%m.%Y %H:%M:%S'),
                    )
                    Receipt.objects.update_or_create(  # TODO: batch_update_or_create ?
                        code=row['receipt_code'],
                        defaults=dict(
                            dttm=dttm,
                            dt=dttm.date(),
                            shop_id=shop_id,
                            data_type=self.data_type,
                            info=row.to_json(),
                        )
                    )
        finally:
            f.close()

        return load_errors


SYSTEM_IMPORT_STRATEGIES_DICT = {
    SystemImportStrategy.POBEDA_IMPORT_SHOP_MAPPING: PobedaImportShopMapping,
    SystemImportStrategy.POBEDA_IMPORT_PURCHASES: PobedaImportPurchases,
    SystemImportStrategy.POBEDA_IMPORT_BRAK: PobedaImportBrak,
    SystemImportStrategy.POBEDA_IMPORT_DELIVERY: PobedaImportDelivery,
}
