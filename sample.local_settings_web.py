DEBUG = False

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
QOS_DEV_CSRF_DISABLED = True
DCS_SESSION_COOKIE_SAMESITE = 'none'

EXTERNAL_HOST = 'https://client.mindandmachine.ru'

METABASE_SITE_URL = f'{EXTERNAL_HOST}/metabase'
METABASE_SECRET_KEY = '8bd7883357009ffe67ac57a3a0a182dcd42a5004b1bc4a00481b4551b5e7ccff'

# mailhog settings
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
EMAIL_HOST = 'mailhog.mindandmachine.ru'
EMAIL_PORT = 1025
EMAIL_USE_TLS = False

# CELERY_TIMEZONE = 'Europe/Moscow'

#SET_USER_PASSWORD_AS_LOGIN=True
#FISCAL_SHEET_DIVIDER_ALIAS = 'nahodka'

#COMPANY_NAME = 'company'
