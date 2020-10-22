"""
config importance
1. djconfig_local (the most important)
2. djconfig
3. config_local
4. config
"""

import os
import sys

from celery.schedules import crontab

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

QOS_CAMERA_KEY = '1'

HOST_IP = '127.0.0.1:8000' # dev
TIMETABLE_IP = "127.0.0.1:5000"


SECRET_KEY = '2p7d00y99lhyh1xno9fgk6jd4bl8xsmkm23hq4vj811ku60g7dsac8dee5rn'
MDAUDIT_AUTHTOKEN_SALT = 'DLKAXGKFPP57B2NEQ4NLB2TLDT3QR20I7QKAGE8I'

'''
Переменная хранящая почты для рассылки отчетов по УРВ. Если None то отчеты не рассылаются
Формат
{
    'network_code': [
        'email@example.com', 
        'email2@example.com'
    ]
}
'''
URV_STAT_EMAILS = None

URV_STAT_SEND_HOUR = 1
URV_STAT_SEND_MINUTE = 0
URV_STAT_SHOP_LEVEL = 2
URV_STAT_SEND_TODAY_HOUR = 3
URV_STAT_SEND_TODAY_MINUTE = 0
MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE = False  # отправлять ли запрос по связке юзера и магазина при сохранении workerday
MDA_PUBLIC_API_HOST = 'https://example.com'
MDA_PUBLIC_API_AUTH_TOKEN = 'dummy'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'django_filters',
    'rest_auth',
    'rest_framework.authtoken',
    'src',
    'src.base',
    'src.forecast',
    'src.timetable',
    'src.main',
    'django_celery_beat',
    'src.celery',
    'fcm_django',
]

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.BasicAuthentication',
        'src.base.auth.authentication.WFMSessionAuthentication',
    ]
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
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

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
        'simple': {
            'format': '%(levelname)s %(asctime)s %(message)s'
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'file': {
            'level': 'INFO',  # use INFO for not logging sql queries
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'qos_backend.log',  # directory with logs must be already created
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
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        # 'django.db.backends': {
        #     'level': 'DEBUG',
        #     'handlers': ['console'],
        # }
    },
}

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

LOCALE_PATHS = [
    os.path.join(BASE_DIR,  'data/locale')
]

STATIC_URL = '/static/'

MEDIA_URL = '/_i/media/'


SESSION_COOKIE_SECURE = True


# DCS_SESSION_COOKIE_SAMESITE = 'none'  # for md audit

QOS_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S" #'%H:%M:%S %d.%m.%Y'
QOS_DATE_FORMAT = '%Y-%m-%d'
QOS_TIME_FORMAT = '%H:%M:%S'
QOS_SHORT_TIME_FORMAT = '%H:%M'

IS_PUSH_ACTIVE = False # отправляем ли пуши на телефон при уведомлениях

ALLOWED_UPLOAD_EXTENSIONS = ['xlsx', 'xls']

MOBILE_USER_AGENTS = ('QoS_mobile_app', 'okhttp',)

METABASE_SITE_URL = 'metabase-url'
METABASE_SECRET_KEY = 'secret-key'

CELERY_IMPORTS = ('src.celery.tasks',)
CELERY_BROKER_URL = 'redis://localhost:6379'
CELERY_RESULT_BACKEND = 'redis://localhost:6379'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERYD_CONCURRENCY = 2
CELERYD_PREFETCH_MULTIPLIER = 1
BACKEND_QUEUE = 'backend_queue'

# for change celery configs must be before (for BACKEND_QUEUE)
# todo: do normal parameters changer

APPEND_SLASH = False
REBUILD_TIMETABLE_MIN_DELTA = 2

# например, для Ортеки для отображения в отчете нужны показатели только по продавцам-кассирам
UPDATE_SHOP_STATS_WORK_TYPES_CODES = None

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
        'task': 'src.celery.tasks.vacancies_create_and_cancel',
        'schedule': crontab(minute='*/30'),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-workers_hard_exchange': {
        'task': 'src.celery.tasks.workers_hard_exchange',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-allocation-of-time-for-work-on-cashbox': {
        'task': 'src.celery.tasks.allocation_of_time_for_work_on_cashbox',
        'schedule': crontab(day_of_month='1', hour=4, minute=0)
    },
    'task-create-pred-bills': {
        'task': 'src.celery.tasks.create_pred_bills',
        'schedule': crontab(hour=23, minute=0, day_of_month='1'),
        'options': {'queue': BACKEND_QUEUE}
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
        'task': 'src.celery.tasks.update_shop_stats_2_months',
        'schedule': crontab(hour=3, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-update-operation-templates': {
        'task': 'src.celery.tasks.op_type_build_period_clients',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-aggregate-receipts': {
        'task': 'src.celery.tasks.aggregate_timeserie_value',
        'schedule': crontab(hour=0, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-delete-old=receipts': {
        'task': 'src.celery.tasks.clean_timeserie_actions',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-send-urv-stat': {
        'task': 'src.celery.tasks.send_urv_stat',
        'schedule': crontab(hour=URV_STAT_SEND_HOUR, minute=URV_STAT_SEND_MINUTE),
        'options': {'queue': BACKEND_QUEUE}
    },
    'task-send-urv-stat-today': {
        'task': 'src.celery.tasks.send_urv_stat_today',
        'schedule': crontab(hour=URV_STAT_SEND_TODAY_HOUR, minute=URV_STAT_SEND_TODAY_MINUTE),
        'options': {'queue': BACKEND_QUEUE}
    },
}

if 'test' in sys.argv:
    # Disable migrations in test, fill the schema directly
    class MigrationDisabler(dict):
        def __getitem__(self, item):
            return None


    MIGRATION_MODULES = MigrationDisabler()
