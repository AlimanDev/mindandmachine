"""
config importance
1. djconfig_local (the most important)
2. djconfig
3. config_local
4. config
"""

import os
from celery.schedules import crontab


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_config_exists(file_name):
    return os.path.isfile(os.path.join(BASE_DIR, 'src', 'conf', file_name))


if is_config_exists('qosconfig.py'):
    from .qosconfig import *

if is_config_exists('qosconfig_local.py'):
    from .qosconfig_local import *


SECRET_KEY = '2p7d00y99lhyh1xno9fgk6jd4bl8xsmkm23hq4vj811ku60g7dsac8dee5rn'

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'src',
    'src.db',
    'src.main',
    'django_celery_beat',
    'django_celery_results',
    'src.celery',
    'celerybeat_status'
    # 'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'src.middleware.csrf.CsrfMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'src.main.urls'

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

AUTH_USER_MODEL = 'db.User'

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

# emails for sending errors
# TODO: its not working actually because we must deploy our SMTP server or use Google SMTP
# https://stackoverflow.com/questions/6367014/how-to-send-email-via-django/6367458#6367458
ADMINS = [('Name Surname', 'test@test.com'),]


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(levelname)s %(asctime)s %(message)s'
        },
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
            'email_backend': 'django.core.mail.backends.filebased.EmailBackend',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

# LOGGING USAGE:
# import logging
# log = logging.getLogger(__name__)
# log.debug("Some debug message")
# log.info("Some info message")
# log.exception("Exception occurred") # for saving traceback


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = False

USE_L10N = False

USE_TZ = False

STATIC_URL = '/_i/static/'

MEDIA_URL = '/_i/media/'


QOS_DATETIME_FORMAT = '%H:%M:%S %d.%m.%Y'
QOS_DATE_FORMAT = '%d.%m.%Y'
QOS_TIME_FORMAT = '%H:%M:%S'
QOS_SHORT_TIME_FORMAT = '%H:%M'


imports = 'proj.tasks'
CELERY_BROKER_URL = 'redis://localhost:6379'
CELERY_RESULT_BACKEND = 'redis://localhost:6379'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'task-every-30-min-update-queue': {
        'task': 'src.celery.tasks.update_queue',
        'schedule': crontab(minute='*/30'),
    },
    'task-free-all-workers-after-shop-closes': {
        'task': 'src.celery.tasks.release_all_workers',
        'schedule': crontab(hour=2, minute=0)
    },

    'task-update_worker_month_stat': {
        'task': 'src.celery.tasks.update_worker_month_stat',
        'schedule': crontab(day_of_month='1,15', hour=3, minute=0)
    },

    'task-notify-cashiers-lack': {
        'task': 'src.celery.tasks.notify_cashiers_lack',
        'schedule': crontab(hour='*/1')
    },
    'task-allocation-of-time-for-work-on-cashbox': {
        'task': 'src.celery.tasks.allocation_of_time_for_work_on_cashbox',
        'schedule': crontab(day_of_month='1', hour=4, minute=0)
    }
}


if is_config_exists('djconfig_local.py'):
    from .djconfig_local import *
