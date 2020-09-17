
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from django.contrib.auth import login
from rest_framework import serializers

from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Q
from hashlib import md5

from src.base.exceptions import FieldError
from django.conf import settings
from src.base.models import (
    User,
    Shop,
    Employment,
)


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

    def construct_response(self, instance, version='1.0'):
        now_day = timezone.now().date()
        employment = Employment.objects.filter(
            Q(dt_fired__gte=now_day) | Q(dt_fired__isnull=True),
            user_id=instance.id,
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
        def get_token(login):
            salt=settings.MDAUDIT_AUTHTOKEN_SALT
            dt = timezone.now().date().strftime("%Y%m%d")
            return md5(f"{login}:{dt}:{salt}".encode()).hexdigest()

        self.request = request
        self.serializer = self.get_serializer(data=self.request.data, context={'request': request})

        if not request.user.is_authenticated:
            self.serializer.is_valid(raise_exception=True)

            token = get_token(self.serializer.data['username'])
            user = None

            if token == self.serializer.data['token']:
                try:
                    user = User.objects.get(username=self.serializer.data['username'])
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

            login(request, user)
        else:
            employments = Employment.objects.filter(
                Q(dt_fired__gt=timezone.now().date())| Q(dt_fired__isnull=True),
                dt_hired__lte=timezone.now().date(),
                user=request.user,
            )

        user = User.objects.get(id=request.user.id)
        # user = UserConverter.convert(request.user)
        # user['shop_id'] = employments.first().shop_id

        data = self.construct_response(user, version=kwargs.get('version', '1.0'))
        return Response(data)


