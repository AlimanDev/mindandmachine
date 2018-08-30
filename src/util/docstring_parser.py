import types
from inspect import getmembers, isfunction
from src.main.auth import views as auth_views
from src.main.camera import views as camera_views
from src.main.cashbox import views as cashbox_views
from src.main.demand import views as demand_views
from src.main.other import views as other_views


def get_imports():
    views_imports = []
    for name, val in globals().items():
        if isinstance(val, types.ModuleType) and val.__name__ != 'types':
            views_imports.append(val)

    return views_imports


def get_functions():
    imported_modules = get_imports()
    functions_list = []

    for imported in imported_modules:
        functions_list.append([
            func for func in getmembers(imported) if (
                isfunction(func[1]) and func[0] != ('api_method' or 'csrf_exempt')
            )])

    return functions_list
