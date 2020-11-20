import io
import logging
from datetime import timedelta
from uuid import UUID

import xlsxwriter
from django.conf import settings
from django.http.response import HttpResponse
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend
from requests.exceptions import HTTPError
from rest_framework import (
    viewsets,
    exceptions,
    permissions
)
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.response import Response

from src.base.auth.authentication import WFMSessionAuthentication
from src.base.models import User
from src.recognition.api.recognition import Recognition
from src.recognition.authentication import TickPointTokenAuthentication
from src.recognition.models import Tick, TickPhoto, TickPoint, UserConnecter, TickPointToken
from src.recognition.serializers import (
    HashSigninSerializer,
    TickPointSerializer,
    TickSerializer,
    TickPhotoSerializer,
    PostTickSerializer_point,
    PostTickSerializer_user,
    PostTickPhotoSerializer,
    DownloadTickPhotoExcelSerializer,
)
from src.recognition.wfm.serializers import ShopSerializer
from src.timetable.models import (
    AttendanceRecords,
    WorkerDay,
    Employment,
)

logger = logging.getLogger('django')
recognition = Recognition()

USERS_WITH_SCHEDULE_ONLY = getattr(settings, 'USERS_WITH_SCHEDULE_ONLY', True)


class HashSigninAuthToken(ObtainAuthToken):
    authentication_classes = ()
    serializer_class = HashSigninSerializer


class TickPointAuthToken(ObtainAuthToken):
    authentication_classes = ()

    def post(self, request, *args, **kwargs):
        """
        POST /api/v1/token-auth/
        params:
            key
        """
        key = request.POST.get('key')
        if not key:
            raise exceptions.AuthenticationFailed('No key')

        try:
            UUID(key, version=4)
        except ValueError:
            raise exceptions.AuthenticationFailed('Invalid key')

        try:
            tick_point = TickPoint.objects.get(key=key)
        except TickPoint.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid key')

        token = TickPointToken.objects.filter(user=tick_point).first()
        # Only one auth token
        if token:
            raise exceptions.AuthenticationFailed('Для этой точки уже открыта сессия')

        token = TickPointToken.objects.create(user=tick_point)

        return Response({
            'token': token.key,
            'tick_point': TickPointSerializer(tick_point).data,
            'shop': ShopSerializer(tick_point.shop).data
        })


class TickViewStrategy:
    def __init__(self, view):
        self.view = view


class UserAuthTickViewStrategy(TickViewStrategy):
    def get_serializer_class(self):
        return PostTickSerializer_user

    def filter_qs(self, queryset):
        user = self.view.request.user
        queryset = queryset.filter(
            user_id=user.id,
        )
        return queryset

    def get_user_id_and_tick_point(self, data):
        user_id = self.view.request.user.id
        shop = data['shop_code']
        tick_point = TickPoint.objects.filter(shop=shop, dttm_deleted__isnull=True).first()
        if tick_point is None:
            tick_point = TickPoint.objects.create(title=f'autocreate tickpoint {shop.id}', shop=shop)

        return user_id, tick_point


class TickPointAuthTickViewStrategy(TickViewStrategy):
    def get_serializer_class(self):
        return PostTickSerializer_point

    def filter_qs(self, queryset):
        tick_point = self.view.request.user
        queryset = queryset.filter(
            tick_point_id=tick_point.id,
        )
        return queryset

    def get_user_id_and_tick_point(self, data):
        tick_point = self.view.request.user
        user_id = data['user_id']
        return user_id, tick_point


class TickViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    basename = ''

    def get_authenticators(self):
        return [WFMSessionAuthentication, TickPointTokenAuthentication(raise_auth_exc=False), TokenAuthentication()]

    @cached_property
    def strategy(self):
        if isinstance(self.request.user, User):
            return UserAuthTickViewStrategy(self)
        elif isinstance(self.request.user, TickPoint):
            return TickPointAuthTickViewStrategy(self)

        raise NotImplementedError

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return self.strategy.get_serializer_class()
        else:
            return TickSerializer

    def get_queryset(self):
        """
        GET /api/v1/ticks
        """

        dttm_from = now().replace(hour=0, minute=0, second=0)
        dttm_to = dttm_from + timedelta(days=1)

        queryset = Tick.objects.all().filter(
            dttm__gte=dttm_from,
            dttm__lte=dttm_to,
            dttm_deleted__isnull=True
        )
        queryset = self.strategy.filter_qs(queryset=queryset)
        return queryset

    def create(self, request, **kwargs):
        """
            POST /api/v1/ticks
            params:
                user_id
                type
                dttm - если отметка оффлайн, сохраняется задним числом
            Загружает фотографию сотрудника, распознает и сохраняет в Tick и AttendanceRecords
        """
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        user_id, tick_point = self.strategy.get_user_id_and_tick_point(data)
        check_time = now() + timedelta(hours=tick_point.shop.get_tz_offset())

        is_front = False
        if 'dttm' in data:
            check_time = data['dttm']
            is_front = True
        dttm_from = check_time.replace(hour=0, minute=0, second=0)
        dttm_to = dttm_from + timedelta(days=1)

        # Проверка на принадлежность пользователя правильному магазину
        employment = Employment.objects.get_active(
            request.user.network.id,
            dttm_from, dttm_to,
            user_id=user_id,
            shop_id=tick_point.shop_id
        ).first()

        wd = WorkerDay.objects.all().filter(
            worker_id=user_id,
            shop_id=tick_point.shop_id,
            employment=employment,
            dttm_work_start__gte=dttm_from,
            dttm_work_end__lte=dttm_to,
            worker_day_details__work_type__shop_id=tick_point.shop_id
        ).first()

        if not wd and USERS_WITH_SCHEDULE_ONLY:
            return Response({"error": "Сотрудник не работает в этом магазине"}, 404)

        tick = Tick.objects.create(
            user_id=user_id,
            tick_point_id=tick_point.id,
            # worker_day=wd,
            lateness=check_time - wd.dttm_work_start if wd else timedelta(seconds=0),
            dttm=check_time,
            type=data['type'],
            is_front=is_front
        )

        if settings.TRUST_TICK_REQUEST:
            AttendanceRecords.objects.create(
                user_id=tick.user_id,
                dttm=check_time,
                verified=True,
                shop_id=tick.tick_point.shop_id,
                type=tick.type,
            )

        return Response(TickSerializer(tick).data)


class TickPhotoViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    basename = ''
    serializer_class = TickPhotoSerializer

    def get_authenticators(self):
        return [WFMSessionAuthentication, TickPointTokenAuthentication(raise_auth_exc=False), TokenAuthentication()]

    def create(self, request, **kwargs):
        """
            POST /api/v1/tick_photos
            params:
                tick_id
                image
                type
                dttm - если отметка оффлайн, сохраняется задним числом
            Загружает фотографию сотрудника, распознает и сохраняет в Tick и AttendanceRecords
        """

        serializer = PostTickPhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        tick_id = data['tick_id']
        image = data['image']
        type = data['type']

        try:
            tick = Tick.objects.get(id=tick_id)
        except Tick.DoesNotExist as e:
            return Response({"error": "Отметка не существует"}, 404)
        tick_point = tick.tick_point

        try:
            tick_photo = TickPhoto.objects.get(tick_id=tick_id, type=type)
            return Response(TickPhotoSerializer(tick_photo).data)
        except TickPhoto.DoesNotExist:
            pass

        check_time = now() + timedelta(hours=tick_point.shop.get_tz_offset())

        is_front = False

        if 'dttm' in data:
            check_time = data['dttm']
            is_front = True

        tick_photo = TickPhoto.objects.create(
            image=image,
            tick_id=tick_id,
            dttm=check_time,
            type=type,
            is_front=is_front
        )

        user_connecter = None
        try:
            user_connecter = UserConnecter.objects.get(user_id=tick.user_id)
        except UserConnecter.DoesNotExist:
            if type == TickPhoto.TYPE_SELF:
                try:
                    partner_id = recognition.create_person({"id": tick.user_id})
                    photo_id = recognition.upload_photo(partner_id, image)
                except HTTPError as e:
                    return Response({"error": str(e)}, e.response.status_code)

                user_connecter = UserConnecter.objects.create(
                    user_id=tick.user_id,
                    partner_id=partner_id,
                )
                tick.user.avatar = image
                tick.user.save()

        if user_connecter:
            try:
                res = recognition.detect_and_match(user_connecter.partner_id, image)
            except HTTPError as e:
                r = Response({"error": str(e)})
                r.status_code = e.response.status_code
                return r

            tick_photo.verified_score = res['score']
            tick_photo.liveness = res['liveness']
            tick_photo.save()
            if type == TickPhoto.TYPE_SELF:
                tick.verified_score = tick_photo.verified_score
                tick.save()

        if (type == TickPhoto.TYPE_SELF) and (tick_photo.verified_score > 0):
            AttendanceRecords.objects.create(
                user_id=tick.user_id,
                dttm=check_time,
                verified=True,
                shop_id=tick.tick_point.shop_id,
                type=tick.type,
            )
        return Response(TickPhotoSerializer(tick_photo).data)

    @action(detail=False, methods=['get'])
    def download(self, request):
        if not request.user.is_superuser:
            return Response(status=403)
        filters = DownloadTickPhotoExcelSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        tick_filter = {}
        if filters.validated_data.get('dt_from', False):
            tick_filter['dttm__date__gte'] = filters.validated_data.get('dt_from')
        if filters.validated_data.get('dt_to', False):
            tick_filter['dttm__date__lte'] = filters.validated_data.get('dt_to')
        ticks = TickPhoto.objects.select_related('tick', 'tick__user', 'tick__tick_point').filter(**tick_filter)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        worksheet = workbook.add_worksheet('Лист1')
        worksheet.write(0, 0, 'User')
        worksheet.write(0, 1, 'Type')
        worksheet.write(0, 2, 'Tick point')
        worksheet.write(0, 3, 'Liveness')
        worksheet.write(0, 4, 'Verified score')
        worksheet.write(0, 5, 'Dttm')

        record_types = dict(TickPhoto.RECORD_TYPES)

        row = 1
        for tick in ticks:
            worksheet.write(row, 0, tick.tick.user.__str__())
            worksheet.write(row, 1, record_types.get(tick.type))
            worksheet.write(row, 2, tick.tick.tick_point.title)
            worksheet.write(row, 3, tick.liveness)
            worksheet.write(row, 4, tick.verified_score)
            worksheet.write(row, 5, tick.dttm.strftime('%Y-%m-%dT%H:%M:%S'))
            row += 1

        workbook.close()
        output.seek(0)
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="TickPhoto_{}-{}.xlsx"'.format(
            filters.validated_data.get('dt_from', 'no_dt_from'),
            filters.validated_data.get('dt_to', 'no_dt_to'),
        )

        return response
