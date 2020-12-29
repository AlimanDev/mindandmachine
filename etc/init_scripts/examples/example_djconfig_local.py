DEBUG = True

SECRET_KEY = '2p7d00y99lhyh1xno9fgk6jd4bl8xsmkm23hq4vj811ku60g7dsac8dee5rn'

ALLOWED_HOSTS = [
    '*',
]

# save logs to ordinary unix log directory
from .djconfig import LOGGING
LOGGING['handlers']['file']['filename'] = '/var/log/qos_backend/qos_backend.log'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'qos_v1',
        'USER': 'qos_v1_user',
        'PASSWORD': '1',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    }
}

# logging sql queries
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        }
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    }
}

CELERY_TASK_ALWAYS_EAGER = True
