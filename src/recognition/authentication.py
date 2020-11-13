from rest_framework import authentication
from rest_framework import exceptions

from .models import TickPointToken


class TickPointTokenAuthentication(authentication.TokenAuthentication):
    model = TickPointToken

    def __init__(self, raise_auth_exc=True, **kwargs):
        self.raise_auth_exc = raise_auth_exc
        super(TickPointTokenAuthentication, self).__init__(**kwargs)

    def authenticate_credentials(self, key):
        try:
            return super(TickPointTokenAuthentication, self).authenticate_credentials(key)
        except exceptions.AuthenticationFailed:
            if self.raise_auth_exc:
                raise
