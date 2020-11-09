from rest_framework import authentication

from .models import TickPointToken


class TickPointTokenAuthentication(authentication.TokenAuthentication):
    model = TickPointToken
