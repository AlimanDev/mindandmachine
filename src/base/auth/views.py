from django.conf import settings
from django.contrib.auth import login
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from src.base.auth.authentication import CsrfExemptSessionAuthentication
from src.base.exceptions import FieldError
from src.base.models import (
    User,
    Employment,
)
from src.util.utils import generate_user_token


class WFMTokenUserSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    token = serializers.CharField(required=True)


class WFMTokenLoginView(GenericAPIView):
    """
    Авторизация
    Args:
        method: POST
        url: api/auth/signin
        username(str):
        password(stt):
    Returns:
        (User): user instance
    """
    error_messages = {
        'no_user': _('There is no such user'),
        'bad_token': _('Unable to log in with provided credentials.')
    }

    serializer_class = WFMTokenUserSerializer
    authentication_classes = (CsrfExemptSessionAuthentication, )

    def construct_response(self, instance, version='1.0'):
        now_day = timezone.now().date()
        employment = Employment.objects.filter(
            Q(dt_fired__gte=now_day) | Q(dt_fired__isnull=True),
            employee__user_id=instance.id,
        ).order_by('dt_hired').first()

        shop_id = employment.shop_id if employment else None

        if version == '0.9':  # old
            user = {
                "code": 200,
                "data": {
                    "id": instance.id,
                    "username": instance.username,
                    "first_name": instance.first_name or '',
                    "last_name": instance.last_name or '',
                    "middle_name": instance.middle_name or '',
                    "avatar_url": instance.avatar.url  if instance.avatar else None,
                    "sex": instance.sex,
                    "phone_number": instance.phone_number or '',
                    "email": instance.email,
                    "shop_id": shop_id,
                },
                "info": None
            }
        else:
            user = {
                "id": instance.id,
                "username": instance.username,
                "first_name": instance.first_name or '',
                "last_name": instance.last_name or '',
                "middle_name": instance.middle_name or '',
                "avatar_url": instance.avatar.url if instance.avatar else None,
                "sex": instance.sex,
                "phone_number": instance.phone_number or '',
                "email": instance.email,
                "shop_id": shop_id,
            }
        return user

    def post(self, request, *args, **kwargs):
        self.request = request
        self.serializer = self.get_serializer(data=self.request.data, context={'request': request})

        if not request.user.is_authenticated:
            self.serializer.is_valid(raise_exception=True)

            username = self.serializer.data['username']
            if settings.CASE_INSENSITIVE_AUTH:
                username = username.lower()
            token = generate_user_token(username)

            if token == self.serializer.data['token']:
                try:
                    lookup_str = 'username'
                    if settings.CASE_INSENSITIVE_AUTH:
                        lookup_str = 'username__iexact'
                    user = User.objects.get(**{lookup_str: username})
                except User.DoesNotExist:
                    raise FieldError(self.error_messages['no_user'])
            else:
                _('Unable to log in with provided credentials.')
                raise FieldError(self.error_messages['bad_token'])
            # employments = Employment.objects.filter(
            #     Q(dt_fired__gt=timezone.now().date())| Q(dt_fired__isnull=True),
            #     dt_hired__lte=timezone.now().date(),
            #     user=user,
            # )
            # if not employments.exists():
            #     return JsonResponse.not_active_error()

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        else:
            employments = Employment.objects.filter(
                Q(dt_fired__gt=timezone.now().date())| Q(dt_fired__isnull=True),
                dt_hired__lte=timezone.now().date(),
                employee__user=request.user,
            )

        user = User.objects.get(id=request.user.id)
        # user = UserConverter.convert(request.user)
        # user['shop_id'] = employments.first().shop_id

        data = self.construct_response(user, version=kwargs.get('version', '1.0'))
        return Response(data)


class OneTimePassView(APIView):
    def get(self, *args, **kwargs):
        return HttpResponseRedirect(redirect_to=settings.EXTERNAL_HOST + '/')
