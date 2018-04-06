def group_by(collection, group_key, sort_key=None, sort_reverse=False):
    result = {}
    for obj in collection:
        k = group_key(obj)
        if k not in result:
            result[k] = []

        result[k].append(obj)

    if sort_key is not None:
        for k, v in result.items():
            v.sort(key=sort_key, reverse=sort_reverse)

    return result


def range_u(start, end, step):
    curr = start
    while curr <= end:
        yield curr
        curr += step


def count(collection, comparer):
    c = 0
    for x in collection:
        if comparer(x):
            c += 1
    return c
