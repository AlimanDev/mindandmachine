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

# def group_by_object(collection, group_key):
#     result = {}
#     for obj in collection:
#         k = group_key(obj)
#         if k not in result:
#             result[k] = obj
#
#     return result

