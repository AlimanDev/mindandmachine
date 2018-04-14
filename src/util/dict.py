class DictUtil(object):
    @staticmethod
    def get_not_none(self, key, default):
        value = self.get(key)
        return value if value is not None else default
