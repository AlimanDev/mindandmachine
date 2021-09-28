"""
config importance
1. djconfig_local (the most important)
2. djconfig
3. config_local
4. config
"""

import os
import sys

import environ
from celery.schedules import crontab

env = environ.Env()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_config_exists(file_name):
    return os.path.isfile(os.path.join(BASE_DIR, 'src', 'conf', file_name))


QOS_DEV_STATIC_ENABLED = False
QOS_DEV_CSRF_DISABLED = False
QOS_DEV_AUTOLOGIN_ENABLED = False
QOS_DEV_AUTOLOGIN_USERNAME = None
QOS_DEV_AUTOLOGIN_PASSWORD = None
# переменная указывающая как матчить табельный номер при загрузке расписания (через User или через Employment)
UPLOAD_TT_MATCH_EMPLOYMENT = True
# создаем employee при загрузке или двух разных юзеров, фикс для граната
UPLOAD_TT_CREATE_EMPLOYEE = True

QOS_CAMERA_KEY = '1'

HOST = env.str('HOST', default='http://127.0.0.1:8000')
EXTERNAL_HOST = env.str('EXTERNAL_HOST', default=HOST)
TIMETABLE_IP = env.str('TIMETABLE_IP', default='127.0.0.1:5000')

# доменное имя проекта, используется в src.timetable.vacancy в письмах
DOMAIN = ''

SECRET_KEY = '2p7d00y99lhyh1xno9fgk6jd4bl8xsmkm23hq4vj811ku60g7dsac8dee5rn'
MDAUDIT_AUTHTOKEN_SALT = 'DLKAXGKFPP57B2NEQ4NLB2TLDT3QR20I7QKAGE8I'

MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE = False  # отправлять ли запрос по связке юзера и магазина при сохранении workerday
MDA_SYNC_USER_TO_SHOP_DAILY = False  # запускать таск, который будет отправлять все связки на текущий день
MDA_SYNC_DEPARTMENTS = False
MDA_SYNC_DEPARTMENTS_THRESHOLD_SECONDS = (60 * 60) + 10  # 1 час + 10 сек
MDA_PUBLIC_API_HOST = 'https://example.com'
MDA_PUBLIC_API_AUTH_TOKEN = 'dummy'

DEBUG = env.bool('DJANGO_DEBUG', default=True)

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'drf_yasg',
    'corsheaders',
    'rest_framework',
    'django_filters',
    'django_admin_listfilter_dropdown',
    'rangefilter',
    'admin_numeric_filter',
    'rest_auth',
    'rest_framework.authtoken',
    'django_json_widget',
    'src',
    'src.base',
    'src.forecast',
    'src.timetable',
    'src.main',
    'django_celery_beat',
    'src.celery',
    'fcm_django',
    'src.recognition',
    'src.integration',
    'src.events',
    'src.notifications',
    'src.reports',
    'import_export',
    'src.tasks',
    'polymorphic',
    'src.exchange',
]

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'src.base.auth.authentication.WFMSessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework_xml.renderers.XMLRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
        'rest_framework_xml.parsers.XMLParser',
    ],
}
OLD_PASSWORD_FIELD_ENABLED=True

FCM_DJANGO_SETTINGS = {
    "FCM_SERVER_KEY": "AAAAoJJLEXM:APA91bHcdiVZxmJE26xjLgYHmmVF03BgEt5r05uJN0kITq_buvZKI26jxGQP-qNAA2FjJdYNI21n_ECtBiisVlIZnCxaF8csG3AW5AXB1BoQiBsn4PlXLFOr1XcxA0cMD3pbwCifWGb0",
     # true if you want to have only one active device per registered user at a time
     # default: False
    "ONE_DEVICE_PER_USER": False,
     # devices to which notifications cannot be sent,
     # are deleted upon receiving error response from FCM
     # default: False
    "DELETE_INACTIVE_DEVICES": False,
}

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django_cookies_samesite.middleware.CookiesSameSite',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'src.util.csrf.CsrfMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'sesame.middleware.AuthenticationMiddleware',
    # 'src.main.auth.middleware.JWTAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'src.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'src/templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env.str('DB_NAME', default='qos'),
        'USER': env.str('DB_USER', default='root'),
        'PASSWORD': env.str('DB_PASSWORD', default='root'),
        'HOST': env.str('DB_HOST', default='localhost'),
        'PORT': '5432',
    }
}

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'sesame.backends.ModelBackend',
]

AUTH_USER_MODEL = 'base.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


ADMINS = [
    ('Robot', 'robot@mindandmachine.ru'),
    ('alex', 'a.aleskin@mindandmachine.ru'),
]
MANAGERS = ADMINS

# To send messages, you must put in the mode DEBUG = False
# For use TLS
EMAIL_USE_TLS = True
EMAIL_PORT = 587

# For use SSL
# EMAIL_USE_SSL = True
# EMAIL_PORT = 465

DEFAULT_FROM_EMAIL = 'robot@mindandmachine.ru'
EMAIL_HOST = 'smtp.yandex.ru'
EMAIL_HOST_USER = 'robot@mindandmachine.ru'
EMAIL_HOST_PASSWORD = 'TjP6szfJe0PpLNH'

SERVER_EMAIL = EMAIL_HOST_USER


SFTP_IP = '212.109.194.87'
SFTP_USERNAME = ''
SFTP_PASSWORD = ''
SFTP_PATH = '~/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname} {module} {process:d} {thread:d}]: {message}',
            'style': '{',
        },
        'simple': {
            'format': '%(levelname)s %(process)d %(asctime)s %(message)s'
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        'django_request': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs/django_request.log'),  # directory with logs must be already created
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'simple',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'email_backend': 'django.core.mail.backends.smtp.EmailBackend',
            'formatter': 'simple',
            'filters': ['require_debug_false'],
            'include_html': True
        },
    },
    'loggers': {
        'django': {
          'handlers': ['console'],
          'level': 'INFO',
        },
        'django.request': {
            'handlers': ['django_request', 'mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        #'django.db.backends': {
        #    'handlers': ['console'],
        #    'level': 'DEBUG',
        #}
    },
}

def add_logger(name, level='DEBUG', formatter='simple', extra_handlers : list=None):
    LOGGING['handlers'][name] = {
        'level': level,
        'class': 'logging.handlers.WatchedFileHandler',
        'filename': os.path.join(BASE_DIR, 'logs', name + '.log'),
        'formatter': formatter,
    }
    LOGGING['loggers'][name] = {
        'handlers': [name],
        'level': level,
        'propagate': True,
    }
    if extra_handlers:
        LOGGING['loggers'][name]['handlers'].extend(extra_handlers)

add_logger('clean_wdays')
add_logger('send_doctors_schedule_to_mis')
add_logger('calc_timesheets', extra_handlers=['mail_admins'])
add_logger('send_doctors_schedule_to_mis', extra_handlers=['mail_admins'])
add_logger('mda_integration', extra_handlers=['mail_admins'])
add_logger('algo_set_timetable', level='DEBUG' if DEBUG else 'INFO')

# LOGGING USAGE:
# import logging
# log = logging.getLogger(__name__)
# log.debug("Some debug message")
# log.info("Some info message")
# log.exception("Exception occurred") # for saving traceback


LANGUAGE_CODE = 'ru-RU'

TIME_ZONE = 'UTC'

USE_I18N = True 

USE_L10N = False 

USE_TZ = False

DATETIME_FORMAT = "d b, Y, H:i:s"

LOCALE_PATHS = [
    os.path.join(BASE_DIR,  'data/locale')
]

STATIC_ROOT = os.path.join(BASE_DIR, 'static/')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

STATIC_URL = '/static/'
MEDIA_URL = '/_i/media/'

FILE_UPLOAD_PERMISSIONS = 0o644

SESSION_COOKIE_SECURE = True

REDOC_SETTINGS = {
    'PATH_IN_MIDDLE': True,
    'HIDE_HOSTNAME': True,
}

SWAGGER_SETTINGS = {
    'TAGS_SORTER': 'alpha',
    'OPERATIONS_SORTER': 'alpha',
    'DEFAULT_AUTO_SCHEMA_CLASS': "src.util.openapi.auto_schema.WFMAutoSchema",
    'DEFAULT_FIELD_INSPECTORS': [
        'src.util.openapi.inspectors.OverrideExampleInspector',
        'drf_yasg.inspectors.CamelCaseJSONFilter',
        'drf_yasg.inspectors.ReferencingSerializerInspector',
        'drf_yasg.inspectors.RelatedFieldInspector',
        'drf_yasg.inspectors.ChoiceFieldInspector',
        'drf_yasg.inspectors.FileFieldInspector',
        'drf_yasg.inspectors.DictFieldInspector',
        'drf_yasg.inspectors.JSONFieldInspector',
        'drf_yasg.inspectors.HiddenFieldInspector',
        'drf_yasg.inspectors.RecursiveFieldInspector',
        'drf_yasg.inspectors.SerializerMethodFieldInspector',
        'drf_yasg.inspectors.SimpleFieldInspector',
        'drf_yasg.inspectors.StringDefaultFieldInspector',
    ],
}

# какие методы и модели могут попасть в описание интеграции
OPENAPI_INTEGRATION_MODELS_METHODS = [
    ('user', 'update'),
    ('department', 'update'),
    ('employment', 'update'),
    ('worker_position', 'update'),
    ('worker_day', 'list'),
    ('timeserie_value', 'create'),
    ('receipt', 'update'),
]

# DCS_SESSION_COOKIE_SAMESITE = 'none'  # for md audit

QOS_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S" #'%H:%M:%S %d.%m.%Y'
QOS_DATE_FORMAT = '%Y-%m-%d'
QOS_TIME_FORMAT = '%H:%M:%S'
QOS_SHORT_TIME_FORMAT = '%H:%M'

IS_PUSH_ACTIVE = False # отправляем ли пуши на телефон при уведомлениях

ALLOWED_UPLOAD_EXTENSIONS = ['xlsx', 'xls']

MOBILE_USER_AGENTS = ('QoS_mobile_app', 'okhttp',)

METABASE_SITE_URL = env.str('METABASE_SITE_URL', default='metabase-url')
METABASE_SECRET_KEY = env.str('METABASE_SECRET_KEY', default='secret-key')

CELERY_IMPORTS = (
    'src.celery.tasks',
    'src.integration.tasks',
    'src.integration.mda.tasks',
    'src.base.shop.tasks',
    'src.events.tasks',
    'src.forecast.load_template.tasks',
    'src.forecast.receipt.tasks',
    'src.timetable.shop_month_stat.tasks',
    'src.timetable.vacancy.tasks',
    'src.timetable.worker_day.tasks',
    'src.timetable.timesheet.tasks',
)

REDIS_HOST = env.str('REDIS_HOST', default='localhost')
CELERY_BROKER_URL = 'redis://' + REDIS_HOST + ':6379'
CELERY_RESULT_BACKEND = 'redis://' + REDIS_HOST + ':6379'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERYD_CONCURRENCY = 2
CELERYD_PREFETCH_MULTIPLIER = 1
BACKEND_QUEUE = env.str('BACKEND_QUEUE', default='backend_queue')

# for change celery configs must be before (for BACKEND_QUEUE)
# todo: do normal parameters changer

APPEND_SLASH = False
REBUILD_TIMETABLE_MIN_DELTA = 2

# например, для Ортеки для отображения в отчете нужны показатели только по продавцам-кассирам
UPDATE_SHOP_STATS_WORK_TYPES_CODES = None

# docker volume create jod_converter_conf
# docker run \
# 	--memory 512m \
# 	--name jod-converter \
# 	-v jod_converter_conf:/etc/app \
# 	--restart unless-stopped \
# 	-p 8030:8080 \
#   -d \
# 	eugenmayer/kontextwork-converter:production
JOD_CONVERTER_URL = env.str('JOD_CONVERTER_URL', default='http://localhost:8030')

# docker run --restart unless-stopped -p 3001:3000 -d thecodingmachine/gotenberg:6
GOTENBERG_URL = env.str('GOTENBERG_URL', default='http://localhost:3001')

ZKTECO_HOST = ''
ZKTECO_KEY = ''
ZKTECO_DEPARTMENT_CODE = 1 # код отдела из zkteco к которому привязываются новые юзеры

# Используем ли интеграцию в проекте
ZKTECO_INTEGRATION = False
# Игнорировать отметки без подтвержденного планового рабочего дня
ZKTECO_IGNORE_TICKS_WITHOUT_WORKER_DAY = True
# смещение id пользователя в ZKTeco чтобы не пересекались
ZKTECO_USER_ID_SHIFT = 10000

RECOGNITION_PARTNER = 'Tevian'

TEVIAN_URL = "https://backend.facecloud.tevian.ru/api/v1/"
TEVIAN_EMAIL = 'a.aleskin@mindandmachine.ru'
TEVIAN_PASSWORD = 'BIQL8pjMUY'
TEVIAN_DATABASE_ID = 26  # TESTURV database
TEVIAN_FD_THRESHOLD = 0.8
TEVIAN_FR_THRESHOLD = 0.8

# после какого времени (в днях) удалять биометрию уволенных сотрудников
URV_DELETE_BIOMETRICS_DAYS_AFTER_FIRED = 365 * 3

TRUST_TICK_REQUEST = False
USERS_WITH_SCHEDULE_ONLY = False
# игнорировать отметку без активного трудоустройства или вакансии
USERS_WITH_ACTIVE_EMPLOYEE_OR_VACANCY_ONLY = False

CALCULATE_LOAD_TEMPLATE = False # параметр отключающий автоматический расчет нагрузки

CLIENT_TIMEZONE = 3

DADATA_TOKEN = None
FILL_SHOP_CITY_FROM_COORDS = False
FILL_SHOP_CITY_COORDS_ADDRESS_TIMEZONE_FROM_FIAS_CODE = False

DATA_UPLOAD_MAX_NUMBER_FIELDS = 10240

SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE = False  # посылать в МИС событийно расписание врачей при его изменении
MIS_USERNAME = None
MIS_PASSWORD = None

CASE_INSENSITIVE_AUTH = False

IMPORT_EXPORT_USE_TRANSACTIONS = True

# Eсли у пользователя пароль пустой, то при сохранении устанавливать пароль как логин
SET_USER_PASSWORD_AS_LOGIN = False

SESAME_ONE_TIME = True
SESAME_MAX_AGE = 60 * 60  # время жизни временного токена 1 час
SESAME_TOKEN_NAME = 'otp_token'

# Возможные вариант можно найти по FISCAL_SHEET_DIVIDERS_MAPPING
# Если == None, то при расчете табеля разделение на осн. и доп. не производится
FISCAL_SHEET_DIVIDER_ALIAS = None

if is_config_exists('djconfig_local.py'):
    from .djconfig_local import *

CELERY_TASK_DEFAULT_QUEUE = BACKEND_QUEUE

CELERY_QUEUES = {
    BACKEND_QUEUE: {
        "exchange": BACKEND_QUEUE,
        "routing_key": BACKEND_QUEUE,
    }
}

CELERY_ROUTES = {
    'src.app.tasks.*': {
        'queue': BACKEND_QUEUE,
        'routing_key': BACKEND_QUEUE,
    },
}

CELERY_BEAT_SCHEDULE = {
    'task-every-30-min-update-queue': {
        'task': 'src.celery.tasks.update_queue',
        'schedule': crontab(minute='0,30'),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-free-all-workers-after-shop-closes': {
        'task': 'src.celery.tasks.release_all_workers',
        'schedule': crontab(hour=2, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },

    # 'task-update_worker_month_stat': {
    #     'task': 'src.celery.tasks.update_worker_month_stat',
    #     'schedule': crontab(day_of_month='1,15', hour=0, minute=0),
    #     'options': {'queue': BACKEND_QUEUE}
    # },

    'task-vacancies_create_and_cancel': {
        'task': 'src.timetable.vacancy.tasks.vacancies_create_and_cancel',
        'schedule': crontab(minute='*/30'),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-workers_hard_exchange': {
        'task': 'src.timetable.vacancy.tasks.workers_hard_exchange',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-allocation-of-time-for-work-on-cashbox': {
        'task': 'src.celery.tasks.allocation_of_time_for_work_on_cashbox',
        'schedule': crontab(day_of_month='1', hour=4, minute=0)
    },
    'task-clean-camera-stats': {
        'task': 'src.celery.tasks.clean_camera_stats',
        'schedule': crontab(day_of_week=6, hour=0, minute=15),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-update-visitors-info': {
        'task': 'src.celery.tasks.update_visitors_info',
        'schedule': crontab(minute='0,30'),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-update-shop-stats': {
        'task': 'src.timetable.shop_month_stat.tasks.update_shop_stats_2_months',
        'schedule': crontab(hour=3, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-update-operation-templates': {
        'task': 'src.celery.tasks.op_type_build_period_clients',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-aggregate-receipts': {
        'task': 'src.forecast.receipt.tasks.aggregate_timeserie_value',
        'schedule': crontab(hour=0, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-delete-old-receipts': {
        'task': 'src.forecast.receipt.tasks.clean_timeserie_actions',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-trigger-cron-report': {
        'task': 'src.reports.tasks.cron_report',
        'schedule': crontab(minute='*/1'),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-delete-inactive-employment-group': {
        'task': 'src.celery.tasks.delete_inactive_employment_groups',
        'schedule': crontab(hour=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-fill-active-shops-schedule': {
        'task': 'src.base.shop.tasks.fill_active_shops_schedule',
        'schedule': crontab(hour=1, minute=30),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-calculate-shop-load-at-night': {
        'task': 'src.forecast.load_template.tasks.calculate_shop_load_at_night',
        'schedule': crontab(hour=0, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-send-employee-not-checked-in-notification': {
        'task': 'src.celery.tasks.employee_not_checked',
        'schedule': crontab(minute='*/5'),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-auto-delete-biometrics': {
        'task': 'src.celery.tasks.auto_delete_biometrics',
        'schedule': crontab(hour=0, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-calc-timesheets': {
        'task': 'src.timetable.timesheet.tasks.calc_timesheets',
        'schedule': crontab(hour=3, minute=15),
        'options': {'queue': BACKEND_QUEUE}
    },
}

if MDA_SYNC_DEPARTMENTS:
    CELERY_BEAT_SCHEDULE['task-sync-mda-data-all-time'] = {
        'task': 'src.integration.mda.tasks.sync_mda_data',
        'schedule': crontab(hour=1, minute=59),
        'options': {'queue': BACKEND_QUEUE},
        'kwargs': {'threshold_seconds': None},
    }
    CELERY_BEAT_SCHEDULE['task-sync-mda-data-last-changes'] = {
        'task': 'src.integration.mda.tasks.sync_mda_data',
        'schedule': crontab(minute=49),
        'options': {'queue': BACKEND_QUEUE},
        'kwargs': {'threshold_seconds': MDA_SYNC_DEPARTMENTS_THRESHOLD_SECONDS},
    }

if MDA_SYNC_USER_TO_SHOP_DAILY:
    CELERY_BEAT_SCHEDULE['task-sync-mda-user-to-shop-relation'] = {
        'task': 'src.integration.mda.tasks.sync_mda_user_to_shop_relation',
        'schedule': crontab(hour=1, minute=30),
        'options': {'queue': BACKEND_QUEUE}
    }

if ZKTECO_INTEGRATION:
    CELERY_BEAT_SCHEDULE['task-import-urv-zkteco'] = {
        'task': 'src.integration.tasks.import_urv_zkteco',
        'schedule': crontab(minute='*/5'),
        'options': {'queue': BACKEND_QUEUE}
    }
    CELERY_BEAT_SCHEDULE['task-export-workers-zkteco'] = {
        'task': 'src.integration.tasks.export_workers_zkteco',
        'schedule': crontab(minute=0),
        'options': {'queue': BACKEND_QUEUE}
    }
    CELERY_BEAT_SCHEDULE['task-delete-workers-zkteco'] = {
        'task': 'src.integration.tasks.delete_workers_zkteco',
        'schedule': crontab(minute=0),
        'options': {'queue': BACKEND_QUEUE}
    }
    CELERY_BEAT_SCHEDULE['task-sync-attendance-areas-zkteco'] = {
        'task': 'src.integration.tasks.sync_att_area_zkteco',
        'schedule': crontab(hour=0, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    }

if 'test' in sys.argv:
    # Disable migrations in test, fill the schema directly
    class MigrationDisabler(dict):
        def __getitem__(self, item):
            return None

    MIGRATION_MODULES = MigrationDisabler()

if DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'].append('rest_framework.renderers.BrowsableAPIRenderer')
