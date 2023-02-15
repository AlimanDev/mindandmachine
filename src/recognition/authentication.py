from rest_framework import authentication
from rest_framework import exceptions

from .models import ShopIpAddress, TickPointToken


class TickPointTokenAuthentication(authentication.TokenAuthentication):
    model = TickPointToken

    def __init__(self, raise_auth_exc=False, **kwargs):
        self.raise_auth_exc = raise_auth_exc
        super(TickPointTokenAuthentication, self).__init__(**kwargs)

    def authenticate(self, request):
        # Cookie
        if token := request.COOKIES.get('auth_token'):
            return self.authenticate_credentials(token)

        # Header
        return super().authenticate(request)

    def authenticate_credentials(self, key):
        try:
            return super(TickPointTokenAuthentication, self).authenticate_credentials(key)
        except exceptions.AuthenticationFailed:
            if self.raise_auth_exc:
                raise

class ShopIPAuthentication(authentication.BaseAuthentication):

    def get_ip_addr(self, request):
        return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
        
    def authenticate(self, request):
       
        ip = self.get_ip_addr(request)

        if not ip:
            return None

        return self.authenticate_credentials(ip)

    def authenticate_credentials(self, ip):
        
        shop_ip = ShopIpAddress.objects.select_related('tick_point__shop__network').filter(ip_address=ip).first()

        if not shop_ip:
            return None

        return (shop_ip, None)
