"""
WSGI config for QoS_backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from src.db.utils import check_func_groups

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.conf.djconfig")

application = get_wsgi_application()

check_func_groups()
