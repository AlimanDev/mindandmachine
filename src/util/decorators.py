from functools import wraps

def cached_method(func):
    """
    Cached method call. Per arguments, that must be hashable.
    Stores in `cached_data` attribute. Proper garbage collection.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not hasattr(self, 'cached_data'):
            self.cached_data = {}
        cache = self.cached_data.setdefault(func.__name__, {})
        key = (*args, *kwargs.values())
        if key not in cache:
            cache[key] = func(self, *args, **kwargs)
        return cache[key]
    return wrapper
