from src.conf.djconfig import LOGGING

LOGGING['handlers']['mail_admins']['email_backend'] = 'django.core.mail.backends.locmem.EmailBackend'
