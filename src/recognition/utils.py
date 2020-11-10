from hashlib import md5

from django.conf import settings
from django.utils.timezone import now


def generate_user_token(login):
    salt = settings.MDAUDIT_AUTHTOKEN_SALT
    dt = now().date().strftime("%Y%m%d")
    return md5(f"{login}:{dt}:{salt}".encode()).hexdigest()
