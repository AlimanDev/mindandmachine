from functools import reduce


def obj_deep_get(obj, *attrs):
    return reduce(lambda o, attr: getattr(o, attr, None), attrs, obj)


def dict_deep_get(dictionary, *keys):
    return reduce(lambda d, key: d.get(key) if d else None, keys, dictionary)
