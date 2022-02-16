import os
from src.conf.djconfig import BASE_DIR

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
            'filename': os.path.join(BASE_DIR, 'logs/django_request.log'),
            # directory with logs must be already created
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'django.request': {
            'handlers': ['django_request'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
