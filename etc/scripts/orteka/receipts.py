import json
from datetime import datetime

import pandas as pd
from django.db.models import OuterRef, Exists

from src.base.models import Employment
from src.forecast.models import Receipt


def strip_val(val):
    return val.strip() if isinstance(val, str) else val


def clean_val(val, strip=True, cast_to=None):
    if strip:
        val = strip_val(val)

    if cast_to:
        val = cast_to(val)

    return val


def upd_differs(differs, data_type, df_val, db_val, cast_to=None):
    df_val = clean_val(df_val, strip=True, cast_to=cast_to)
    db_val = clean_val(db_val, strip=True, cast_to=cast_to)

    if df_val != db_val:
        differs[data_type] = {'df': df_val, 'db': db_val}


def compare_df_and_db(print_not_found_in_df_as_json=False):
    with open('analyze_receipts.log', 'w') as f:
        receipts = Receipt.objects.filter(
            data_type='receipt',
            dttm__gte='2020-10-01 00:00:01.000000',
            dttm__lte='2020-12-03 14:32:00.000000',
        ).select_related(
            'shop',
        ).annotate(
            shop_active_employments_exists=Exists(Employment.objects.get_active(
                1,
                dt_from=OuterRef('dttm__date'),
                dt_to=OuterRef('dttm__date'),
                shop=OuterRef('shop'),
            ))
        ).order_by('dttm')
        df = pd.read_excel('/home/wonder/Documents/orteka/ЧекиМДАудит.xlsx', index_col=7)

        for r in receipts:
            differs = {}
            db_data = json.loads(r.info)
            guid = strip_val(str(r.code))
            try:
                df_data = df.loc[guid]
            except KeyError:
                print(f'guid={guid}, not found in df', file=f)
                if not (r.shop.is_active and (r.shop.dttm_deleted is None or r.shop.dttm_deleted > r.dttm)):
                    print(f'inactive shop with code={r.shop.code}', file=f)
                    continue
                if not r.shop_active_employments_exists:
                    print(f'no active employments in shop with code={r.shop.code}', file=f)
                    continue
                if print_not_found_in_df_as_json:
                    print(json.dumps(db_data, indent=4, ensure_ascii=False), file=f)
                    continue

            upd_differs(differs, 'sum', df_data['Сумма'], db_data.get('СуммаДокумента'), cast_to=float)
            upd_differs(differs, 'receipt_type', df_data['ВидОперации'], db_data.get('ВидОперации'))
            upd_differs(differs, 'shop_code', df_data['КодМагазина'], r.shop.code)

            if differs:
                print(f'guid={guid}, differs={differs}', file=f)
                r_type_differs = differs.get('receipt_type')
                if r_type_differs and r_type_differs.get('df') == 'Возврат' and r_type_differs.get('db') is None:
                    print(json.dumps(db_data, indent=4, ensure_ascii=False), file=f)


def print_sum(shop_code, dttm_from=datetime(2020, 11, 1, 0, 0, 1), dttm_to=datetime(2020, 11, 30, 23, 59, 59)):
    df = pd.read_excel('/home/wonder/Documents/orteka/ЧекиМДАудит.xlsx', index_col=7)
    df = df[
        (pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S') > dttm_from) &
        (pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S') < dttm_to) &
        (df['КодМагазина'] == f'{shop_code}    ')
        # (df['ВидОперации'] == 'Продажа')
        ]
    sum = df.groupby(['КодМагазина'])['Сумма'].sum()
    print(sum)


def print_receipt(guid):
    r = Receipt.objects.filter(code=guid).first()
    db_data = json.loads(r.info)
    print(json.dumps(db_data, indent=4, ensure_ascii=False))
