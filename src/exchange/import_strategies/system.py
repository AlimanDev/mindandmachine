import datetime as dt
import ftplib
import json
import typing as tp

import pandas as pd
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
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
    def __init__(
            self, 
            system_code, 
            system_name, 
            filename, 
            file_format, 
            csv_delimiter, 
            wfm_shop_code_field_name,
            wfm_shop_name_field_name, 
            external_shop_code_field_name, 
            dt_from: tp.Optional[tp.Any] = None, 
            dt_to: tp.Optional[tp.Any] = None, 
            **kwargs):
        self.system_code = system_code
        self.system_name = system_name
        self.filename = filename
        self.file_format = file_format
        self.csv_delimiter = csv_delimiter
        self.wfm_shop_code_field_name = wfm_shop_code_field_name
        self.wfm_shop_name_field_name = wfm_shop_name_field_name
        self.external_shop_code_field_name = external_shop_code_field_name
        super(BaseSystemImportStrategy, self).__init__(**kwargs)

    def _read_file_to_df(self, f):
        if self.file_format == 'xlsx':
            return pd.read_excel(f)
        elif self.file_format == 'csv':
            return pd.read_csv(f, delimiter=self.csv_delimiter)

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
                shop_code = row[
                    self.wfm_shop_code_field_name or self.wfm_shop_name_field_name]
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
    def __init__(self,
                 system_code,
                 data_type,
                 separated_file_for_each_shop,
                 filename_fmt: str,
                 dt_from,
                 dt_to,
                 shop_num_column_name,
                 dt_or_dttm_column_name: str,
                 dt_or_dttm_format: str,
                 csv_delimiter: str,
                 fix_date: bool = False,
                 columns: tp.Optional[tp.List[str]] = None,
                 receipt_code_columns: tp.Optional[tp.List[str]] = None,
                 **kwargs):
        self._dt_provider = DateTimeProvider(generator=None)
        self.fix_date = fix_date
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

    def _init_cached_data(self) -> None:
        self.cached_data = {
            'generic_shop_ids': {g.code: g.object_id for g in
                                 GenericExternalCode.objects.filter(
                                     external_system__code=self.system_code,
                                     object_type=ContentType.objects.get_for_model(Shop),
                                 )},
        }

    def get_shop_id_by_shop_num(self, code) -> tp.Optional[int]:
        shop_id = self.cached_data['generic_shop_ids'].get(code, None)
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
                    dt_and_filename_pairs.append(
                        (dt, self.get_filename(dt, shop_code=shop_code)))
            else:
                dt_and_filename_pairs.append((dt, self.get_filename(dt)))
        return dt_and_filename_pairs

    def execute(self):
        errors = set()
        dt_and_filename_pairs = self.get_dt_and_filename_pairs()

        for dt, filename in dt_and_filename_pairs:
            load_errors = self.load_file(dt, filename)
            if load_errors:
                errors = errors.union(load_errors)
        res = {
            'errors': list(errors),
        }
        return res

    def _get_csv_generator(self, 
                           filename: str, 
                           read_csv_kwargs: tp.Dict[str, tp.Any]
                           ) -> tp.Iterable[pd.DataFrame]:
        """
        encapsulate reading from file by chunks.
        It will be replaced with the appropriate class later"""

        with self.fs_engine.open_file(filename) as f:
            df_chunks = pd.read_csv(f, **read_csv_kwargs)
            for df in df_chunks:
                yield df

    def _insert_into_db(self,
                        object_list_of_tuples: tp.List[tp.Dict[str, tp.Any]],
                        dtt: dt.date,
                        shops_id: tp.Set[str],
                        bulk_chunk_size: int) -> None:
        db_objects = []
        for obj in object_list_of_tuples:
            db_objects.append(
                Receipt(
                    code=obj["code"],
                    dttm=obj["dttm"],
                    dt=dtt,
                    shop_id=obj["shop_id"],
                    data_type=self.data_type,
                    info=obj["info"],
                )
            )
        with transaction.atomic():
            Receipt.objects.filter(dt=dtt,
                                   data_type=self.data_type,
                                   shop_id__in=shops_id).delete()

            Receipt.objects.bulk_create(db_objects, batch_size=bulk_chunk_size)

    def _get_dttm(self, 
                  row: pd.Series, 
                  dtt: dt.date
                  ) -> tp.Tuple[tp.Optional[dt.datetime], tp.Optional[Exception]]:
        """
        we should check a type and a correct form of our date.
        If all is good and data_type is from 'pobeda' then we check
        1. is this date correct:
            the difference between dates is less than 7 days
            (because it's very weird to get the date like that in file
            with the current date)
        2. change the current date to another: get a date from filename
        """
        try:
            dttm = dt.datetime.strptime(
                row[self.dt_or_dttm_column_name],
                self.dt_or_dttm_format,
            )
            if self.fix_date:
                # https://mindandmachine.myjetbrains.com/youtrack/issue/RND-572
                # use a date from a filename pattern
                if abs((dtt - dttm.date()).days) > 7:
                    raise TypeError("Days range between dt and dttm is greater"
                                    f" than 1 week: {dtt} and {dttm.date()}")
                else:
                    dttm = dt.datetime(
                        dtt.year,
                        dtt.month,
                        dtt.day,
                        dttm.hour,
                        dttm.minute,
                        dttm.second
                    )
            return dttm, None
        except TypeError as e:
            return None, e

    def _get_receipt_code(self, obj):
        if self.receipt_code_columns:
            receipt_code = "".join(obj[self.receipt_code_columns].values)
        else:
            receipt_code = hash(tuple(obj))
        return receipt_code

    @staticmethod
    def _create_object(
            row: pd.Series,
            all_columns: tp.List[str],
            unused_columns: tp.List[str]) -> tp.Dict[str, tp.Any]:
        return {
            "code": row['receipt_code'],
            "dttm": row["updated_dttm"],
            "shop_id": row["shop_id"],
            "info": row[set(all_columns) - set(unused_columns)].to_json(),
        }

    def load_file(self,
                  dtt: dt.date,
                  filename: str,
                  chunksize: int = 1000,
                  bulk_chunk_size: int = 10000) -> tp.Set[str]:

        load_errors = set()
        shops_id = set()
        objects = []

        read_csv_kwargs = {
            "dtype": str,
            "delimiter": self.csv_delimiter,
            "chunksize": chunksize
        }

        if self.columns:
            read_csv_kwargs['index_col'] = False
            read_csv_kwargs['names'] = self.columns

        unused_cols = ["index", "shop_id", "updated_dttm", "dttm_error"]

        try:
            for df in self._get_csv_generator(filename, read_csv_kwargs):

                # Hash generation is different in each python
                # launch! Can only compare in receipts imported
                # from the same task

                df["receipt_code"] = df.apply(self._get_receipt_code, axis=1)
                df["index"] = df.index.values
                df['shop_id'] = (df[self.shop_num_column_name]
                                    .apply(self.get_shop_id_by_shop_num))
                df["updated_dttm"] = (
                    df.apply(lambda obj: self._get_dttm(obj, dtt)[0], axis=1))
                df["dttm_error"] = (
                    df.apply(lambda obj: self._get_dttm(obj, dtt)[1], axis=1))

                # update containers with main info

                shops_id |= set(df.loc[~df['shop_id'].isna(), "shop_id"])

                df_for_objects = df[(~df["shop_id"].isna()) & (~df["updated_dttm"].isna())]
                if df_for_objects.shape[0]:
                    objects += (df_for_objects.apply(
                        lambda row: self._create_object(row, df.columns, unused_cols),
                        axis=1).values.tolist())

                # update sets with errors
                df_shop_load_error = df.loc[df["shop_id"].isna(), self.shop_num_column_name]
                if df_shop_load_error.shape[0]:
                    load_errors |= set(
                        df_shop_load_error.apply(
                            lambda x: f"can't map shop_id for shop_num='{x}'"))

                df_dttm_error = df.loc[df["updated_dttm"].isna(), ["dttm_error", "index"]]
                if df_dttm_error.shape[0]:
                    load_errors |= set(
                        df_dttm_error
                        .apply(
                            lambda row: f"{row['dttm_error'].__class__.__name__}: "
                                        f"{str(row['dttm_error'])}: {filename}: "
                                        f"row: {row['index']}",
                            axis=1))

            self._insert_into_db(objects, dtt, shops_id, bulk_chunk_size)

        except (FileNotFoundError, PermissionError, *ftplib.all_errors) as e:
            load_errors.add(f'{e.__class__.__name__}: {str(e)}: {filename}')
        return load_errors

