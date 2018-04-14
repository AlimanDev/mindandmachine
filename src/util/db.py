class CashboxTypeUtil(object):
    @staticmethod
    def sort(types):
        types = {x.name: x for x in types}
        types_result = []

        def __add_t(__s):
            __x = types.pop(__s, None)
            if __x is not None:
                types_result.append(__x)

        __add_t('Линия')
        __add_t('Возврат')
        for x in types.values():
            types_result.append(x)

        return types_result

    @staticmethod
    def fetch_from_cashboxes(cashboxes):
        types = {}
        for x in cashboxes:
            types[x.type.id] = x.type

        return list(types.values())
