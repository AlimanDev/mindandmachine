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
