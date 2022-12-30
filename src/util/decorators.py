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


LOCK_MODES = {
    'ACCESS SHARE',
    'ROW SHARE',
    'ROW EXCLUSIVE',
    'SHARE UPDATE EXCLUSIVE',
    'SHARE',
    'SHARE ROW EXCLUSIVE',
    'EXCLUSIVE',
    'ACCESS EXCLUSIVE',
}

def require_lock(model, lock):
    """
    Decorator for PostgreSQL's table-level lock functionality
    
    Example:
        @transaction.atomic
        @require_lock(MyModel, 'ACCESS EXCLUSIVE')
        def function():
            ...
    
    PostgreSQL's LOCK Documentation:
    http://www.postgresql.org/docs/8.3/interactive/sql-lock.html
    """
    def require_lock_decorator(func):
        # @wraps(func)
        def wrapper(*args, **kwargs):
            if lock not in LOCK_MODES:
                raise ValueError(f'{lock} is not a PostgreSQL supported lock mode.')
            from django.db import connection
            cursor = connection.cursor()
            cursor.execute(f'LOCK TABLE {model._meta.db_table} IN {lock} MODE')
            return func(*args, **kwargs)
        return wrapper
    return require_lock_decorator
