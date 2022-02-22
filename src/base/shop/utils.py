import pytz
from datetime import datetime
from dateutil.parser import parse
from thefuzz import process, fuzz

def get_tree(shops):
    tree = []
    parent_indexes = {}
    for shop in shops:
        if not shop.parent_id in parent_indexes:
            tree.append({
                "id": shop.id,
                "label": shop.name,
                "tm_open_dict": shop.open_times,
                "tm_close_dict" :shop.close_times,
                "address": shop.address,
                "forecast_step_minutes":shop.forecast_step_minutes,
                "children": []
            })
            parent_indexes[shop.id] = [len(tree) - 1,]
        else:
            root = tree[parent_indexes[shop.parent_id][0]]
            parent = root
            for i in parent_indexes[shop.parent_id][1:]:
                parent = parent['children'][i]
            parent['children'].append({
                "id": shop.id,
                "label": shop.name,
                "tm_open_dict": shop.open_times,
                "tm_close_dict" :shop.close_times,
                "address": shop.address,
                "forecast_step_minutes":shop.forecast_step_minutes,
                "children": []
            })
            parent_indexes[shop.id] = parent_indexes[shop.parent_id].copy()
            parent_indexes[shop.id].append(len(parent['children']) - 1)
    return tree

DEFINED_TIMEZONES = {
    2.0: 'Europe/Kaliningrad',
    3.0: 'Europe/Moscow',
    4.0: 'Europe/Ulyanovsk',
    5.0: 'Asia/Yekaterinburg',
    6.0: 'Asia/Omsk',
    7.0: 'Asia/Novosibirsk',
    8.0: 'Asia/Irkutsk',
    9.0: 'Asia/Yakutsk',
    10.0: 'Asia/Vladivostok',
    12.0: 'Asia/Kamchatka',
}

def get_offset_timezone_dict():
    tz_info = {}
    dt = datetime.now(pytz.utc)
    for tz in pytz.common_timezones:
        tz_info[dt.astimezone(pytz.timezone(tz)).utcoffset().total_seconds() / 3600] = tz
    tz_info.update(DEFINED_TIMEZONES)

    return tz_info

def get_shop_name(name, shops):
    if name in shops:
        return name
    return process.extractOne(name, shops, scorer=fuzz.partial_token_sort_ratio)[0]
