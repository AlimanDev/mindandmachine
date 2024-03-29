import io, logging
from typing import Union
from datetime import timedelta
from uuid import UUID
from django.db.models import Exists, OuterRef, Q

import xlsxwriter
from django.conf import settings
from django.http.response import HttpResponse
from django.utils.translation import gettext as _
from django.utils.functional import cached_property
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend
from django.views.generic.edit import FormView
from django.db.models.fields.files import ImageFieldFile
from drf_yasg.utils import swagger_auto_schema
from requests.exceptions import RequestException
from rest_framework import (
    exceptions,
    permissions, status
)
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination

from src.apps.base.authentication import CsrfExemptSessionAuthentication
from src.apps.base.models import User, Shop, Employee
from src.apps.base.permissions import Permission
from src.apps.base.views_abstract import BaseModelViewSet
from src.interfaces.api.serializers.base import NetworkSerializer
from src.adapters.tevian.recognition import Recognition
from src.apps.recognition.authentication import ShopIPAuthentication, TickPointTokenAuthentication
from src.apps.recognition.models import ShopIpAddress, Tick, TickPhoto, TickPoint, UserConnecter, TickPointToken
from src.apps.recognition.filters import TickPointFilterSet
from src.interfaces.api.serializers.recognition import (
    HashSigninSerializer,
    TickPointSerializer,
    TickSerializer,
    TickPhotoSerializer,
    PostTickSerializer_point,
    PostTickSerializer_user,
    PostTickPhotoSerializer,
    DownloadTickPhotoExcelSerializer, ShopIpAddressSerializer,
)
from src.interfaces.api.serializers.wfm import ShopSerializer
from src.apps.recognition.forms import DownloadViolatorsReportForm
from src.apps.recognition.utils import check_duplicate_biometrics
from src.apps.timetable.models import (
    AttendanceRecords,
    WorkerDay,
    Employment,
)
from src.apps.timetable.mixins import SuperuserRequiredMixin


logger = logging.getLogger('django')
logger_recognition = logging.getLogger('recognition')
recognition = Recognition()

USERS_WITH_SCHEDULE_ONLY = getattr(settings, 'USERS_WITH_SCHEDULE_ONLY', True)

LATENESS_LAMBDA = {
    Tick.TYPE_COMING: lambda check_dttm, wd: check_dttm - wd.dttm_work_start,
    Tick.TYPE_LEAVING: lambda  check_dttm, wd: wd.dttm_work_end - check_dttm,
}


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
        skip_check_urv_token = tick_point and \
                          tick_point.shop_id and \
                          tick_point.shop.network_id and \
                          tick_point.shop.network.settings_values_prop.get('skip_check_urv_token', False)
        if not skip_check_urv_token and token:  # Only one auth token
            raise exceptions.AuthenticationFailed(_('A session is already open for this tick point'))

        token, _tpt_created = TickPointToken.objects.get_or_create(user=tick_point)

        return Response({
            'token': token.key,
            'tick_point': TickPointSerializer(tick_point).data,
            'shop': ShopSerializer(tick_point.shop).data,
            'network': NetworkSerializer(tick_point.shop.network).data,
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

    def get_user_id_employee_id_and_tick_point(self, data):
        user_id = self.view.request.user.id
        shop = data['shop_code']
        tick_point = TickPoint.objects.filter(shop=shop, dttm_deleted__isnull=True).first()
        if tick_point is None:
            tick_point = TickPoint.objects.create(
                name=f'autocreate tickpoint {shop.id}', 
                shop=shop, 
                network_id=self.view.request.user.network_id,
            )

        return user_id, data.get('employee_id'), tick_point


class TickPointAuthTickViewStrategy(TickViewStrategy):
    def get_serializer_class(self):
        return PostTickSerializer_point

    def filter_qs(self, queryset):
        tick_point = self.view.request.user
        queryset = queryset.filter(
            tick_point__shop_id=tick_point.shop_id,
        )
        return queryset

    def get_user_id_employee_id_and_tick_point(self, data):
        tick_point = self.view.request.user
        user_id = data['user_id']
        return user_id, data.get('employee_id'), tick_point


class ShopIPAuthTickViewStrategy(TickPointAuthTickViewStrategy):
    def filter_qs(self, queryset):
        shop_ip = self.view.request.user
        queryset = queryset.filter(
            tick_point__shop_id=shop_ip.shop_id,
        )
        return queryset

    def get_user_id_employee_id_and_tick_point(self, data):
        shop_ip = self.view.request.user
        user_id = data['user_id']
        return user_id, data.get('employee_id'), shop_ip.tick_point_obj


class TickViewSet(BaseModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    basename = ''
    openapi_tags = ['Tick',]

    def get_authenticators(self):
        return [
            ShopIPAuthentication(),
            TickPointTokenAuthentication(raise_auth_exc=False),
            CsrfExemptSessionAuthentication(),
            TokenAuthentication()
        ]

    @cached_property
    def strategy(self):
        if isinstance(self.request.user, User):
            return UserAuthTickViewStrategy(self)
        elif isinstance(self.request.user, TickPoint):
            return TickPointAuthTickViewStrategy(self)
        elif isinstance(self.request.user, ShopIpAddress):
            return ShopIPAuthTickViewStrategy(self)

        raise NotImplementedError

    def get_serializer_class(self):
        if getattr(self, 'swagger_fake_view', False):   # for schema generation metadata
            return TickSerializer

        if self.request.method == 'POST' or self.request.method == 'PUT':
            return self.strategy.get_serializer_class()
        else:
            return TickSerializer

    def get_queryset(self):
        """
        GET /api/v1/ticks
        """
        offset = self.request.user.shop.get_tz_offset() if isinstance(self.request.user, TickPoint) else 0

        dt_from = (now() + timedelta(hours=offset)).date()
        dt_to = dt_from + timedelta(days=1)
        
        today_comming_tick_cond = Tick.objects.filter(
            dttm__date=dt_from,
            type=Tick.TYPE_COMING,
            user_id=OuterRef('user_id'),
            tick_point__shop_id=OuterRef('tick_point__shop_id'),
        )
        yesterday_leaving_tick_cond = Tick.objects.filter(
            dttm__date=(dt_from - timedelta(1)),
            type=Tick.TYPE_LEAVING,
            user_id=OuterRef('user_id'),
            tick_point__shop_id=OuterRef('tick_point__shop_id'),
        )

        queryset = Tick.objects.annotate(
            today_exists=Exists(today_comming_tick_cond),
            yesterday_leaving_exists=Exists(yesterday_leaving_tick_cond),
        ).filter(
            (Q(dttm__date__gte=(dt_from - timedelta(1))) & Q(type=Tick.TYPE_COMING) & Q(today_exists=False) & Q(yesterday_leaving_exists=False)) |
            Q(dttm__date__gte=dt_from, dttm__date__lte=dt_to),
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
        user_id, employee_id, tick_point = self.strategy.get_user_id_employee_id_and_tick_point(data)
        check_time = now() + timedelta(hours=tick_point.shop.get_tz_offset())

        is_front = False
        if 'dttm' in data:
            check_time = data['dttm']
            is_front = True
        dttm_from = check_time.replace(hour=0, minute=0, second=0)
        dttm_to = dttm_from + timedelta(days=1)

        employee_lookup = {}
        if employee_id:
            employee_lookup['employee_id'] = employee_id
        else:
            employee_lookup['employee__user_id'] = user_id

        # Проверка на принадлежность пользователя правильному магазину
        employment = Employment.objects.get_active(
            request.user.network_id,
            dttm_from.date(), dttm_from.date(),
            shop_id=tick_point.shop_id,
            **employee_lookup,
        ).first()

        if (not employment) and settings.USERS_WITH_ACTIVE_EMPLOYEE_OR_VACANCY_ONLY:
            # есть ли вакансия в этом магазине
            wd = WorkerDay.objects.filter(
                shop_id=tick_point.shop_id,
                dt__gte=dttm_from - timedelta(1),
                dt__lte=dttm_to.date(),
                type__is_dayoff=False,
                is_approved=True,
                is_fact=False,
                is_vacancy=True,
                **employee_lookup,
            ).first()
            if not wd:
                return Response(
                    {
                        "error": _("You do not have an active employment at the moment, "
                        "the action can not be performed, please refer to your management")
                    }, 
                    400
                )

        wd = WorkerDay.objects.all().filter(
            **employee_lookup,
            shop_id=tick_point.shop_id,
            employment=employment,
            dttm_work_start__gte=dttm_from,
            dttm_work_end__lte=dttm_to,
            worker_day_details__work_type__shop_id=tick_point.shop_id
        ).first()

        if not wd and USERS_WITH_SCHEDULE_ONLY:
            return Response({"error": _('Today, the employee does not have a working day in this shop')}, 404)

        if employee_id is None and user_id:
            employee = Employee.objects.filter(user_id=user_id).order_by('-id').first()
            if employee:
                employee_id = employee.id

        tick = Tick.objects.create(
            user_id=user_id,
            employee_id=employee_id,
            tick_point_id=tick_point.id,
            dttm=check_time,
            type=data['type'],
            is_front=is_front
        )

        if request.user.network.trust_tick_request:
            AttendanceRecords.objects.create(
                user_id=tick.user_id,
                employee_id=employee_id,
                dttm=check_time,
                verified=True,
                shop_id=tick.tick_point.shop_id,
                type=tick.type,
            )

        return Response(TickSerializer(tick).data)

    def update(self, request, *args, **kwargs):
        try:
            tick = Tick.objects.get(pk=kwargs['pk'])
        except Tick.DoesNotExist as e:
            return Response({"error": _("The tick does not exist")}, 404)

        data = self.get_serializer_class()(data=request.data, context=self.get_serializer_context())
        data.is_valid(raise_exception=True)

        type = data.validated_data.get('type', Tick.TYPE_NO_TYPE)

        if tick.type == Tick.TYPE_NO_TYPE:
            tick.type = type
            if request.user.network.trust_tick_request:
                record, _created = AttendanceRecords.objects.get_or_create(
                    user_id=tick.user_id,
                    employee_id=tick.employee_id,
                    dttm=tick.dttm,
                    verified=True,
                    shop_id=tick.tick_point.shop_id,
                    type=AttendanceRecords.TYPE_NO_TYPE,
                )
                record.type = type
                record.save()
                if record.fact_wd and record.fact_wd.closest_plan_approved:
                    tick.lateness = LATENESS_LAMBDA.get(tick.type, lambda x, y: None)(tick.dttm, record.fact_wd.closest_plan_approved)     
            tick.save()
        
        return Response(TickSerializer(tick).data)


class TickPhotoViewSet(BaseModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    basename = ''
    serializer_class = TickPhotoSerializer
    openapi_tags = ['TickPhoto',]
    http_method_names = ['get', 'post', 'delete']

    def get_authenticators(self):
        return [
            ShopIPAuthentication(),
            TickPointTokenAuthentication(raise_auth_exc=False),
            CsrfExemptSessionAuthentication(),
            TokenAuthentication()
        ]

    @swagger_auto_schema(
        request_body=PostTickPhotoSerializer,
        responses={201: TickPhotoSerializer},
    )
    def create(self, request, **kwargs):
        """
            POST /tevian/v1/tick_photos
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
        tick_id: int = data['tick_id']
        image: ImageFieldFile = data['image']
        tick_type: str = data['type']

        try:
            tick = Tick.objects.select_related('user', 'tick_point__shop').get(id=tick_id)
        except Tick.DoesNotExist as e:
            return Response({"error": _('The tick does not exist')}, 404)
        tick_point = tick.tick_point

        try:
            tick_photo = TickPhoto.objects.get(tick_id=tick_id, type=tick_type)
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
            type=tick_type,
            is_front=is_front
        )

        user_connecter = None
        biometrics = None
        try:
            user_connecter = UserConnecter.objects.get(user_id=tick.user_id)
        except UserConnecter.DoesNotExist:
            if tick_type == TickPhoto.TYPE_SELF:
                tick.user.avatar = image
                tick.user.save()
                try:
                    check_duplicate_biometrics(tick_photo.image, tick.user, tick.tick_point.shop_id)
                    partner_id = recognition.create_person({"id": tick.user_id})
                    recognition.upload_photo(partner_id, tick_photo.image)
                except RequestException as e:
                    msg = recognition.prepare_error_message(e, tick)
                    logger_recognition.exception(msg)
                    biometrics = {'score': 1, 'liveness': 1, 'biometrics_check': False}
                else:
                    user_connecter = UserConnecter.objects.create(
                        user_id=tick.user_id,
                        partner_id=partner_id,
                    )

        if user_connecter:
            try:
                biometrics = recognition.detect_and_match(user_connecter.partner_id, tick_photo.image)
                biometrics['biometrics_check'] = True
            except RequestException as e:
                msg = recognition.prepare_error_message(e, tick)
                logger_recognition.exception(msg)
                biometrics = {'score': 1, 'liveness': 1, 'biometrics_check': False}
        
        if biometrics:
            tick_photo.verified_score: float = biometrics['score']
            tick_photo.liveness: float = biometrics['liveness']
            tick_photo.biometrics_check: bool = biometrics['biometrics_check']
            tick_photo.save()
            if tick_type == TickPhoto.TYPE_SELF:
                tick.verified_score: float = tick_photo.verified_score
                tick.biometrics_check: bool = tick_photo.biometrics_check
                tick.save()

        data = TickPhotoSerializer(tick_photo).data
        data['lateness'] = None
        if (tick_type == TickPhoto.TYPE_SELF) and (tick_photo.verified_score > 0):
            record = AttendanceRecords.objects.create(
                user_id=tick.user_id,
                employee_id=tick.employee_id,
                dttm=tick.dttm,
                verified=True,
                shop_id=tick.tick_point.shop_id,
                type=tick.type,
            )
            if record.fact_wd and record.fact_wd.closest_plan_approved:
                tick.lateness: timedelta = LATENESS_LAMBDA.get(tick.type, lambda x, y: None)(tick.dttm, record.fact_wd.closest_plan_approved)
                tick.save()
                data['lateness']: Union[timedelta, None] = tick.lateness.total_seconds() if tick.lateness else None
        return Response(data)

    @swagger_auto_schema(
        responses={200:'Файл с отметками'},
        operation_description='Запрос на скачивание файла с отметками',
        query_serializer=DownloadTickPhotoExcelSerializer,
    )
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
            worksheet.write(row, 2, tick.tick.tick_point.name)
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


class TickPointViewSet(BaseModelViewSet):
    permission_classes = [Permission]
    filter_backends = [DjangoFilterBackend]
    basename = ''
    serializer_class = TickPointSerializer
    openapi_tags = ['TickPoint', ]
    filterset_class = TickPointFilterSet
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        return TickPoint.objects.filter(network_id=self.request.user.network_id, dttm_deleted__isnull=True)

    def perform_create(self, serializer):
        serializer.save(network_id=self.request.user.network_id)
    
    @action(
        detail=False, 
        methods=['get'], 
        permission_classes=[permissions.IsAuthenticated],
        authentication_classes=[
            ShopIPAuthentication,
            TickPointTokenAuthentication,
        ],
    )
    def current_tick_point(self, request):
        if isinstance(request.user, TickPoint):
            tick_point = request.user
        elif isinstance(request.user, ShopIpAddress):
            tick_point = request.user.tick_point_obj
        else:
            raise NotImplementedError()
        
        return Response({
            'tick_point': TickPointSerializer(tick_point).data,
            'shop': ShopSerializer(tick_point.shop).data,
            'network': NetworkSerializer(tick_point.shop.network).data,
        })


class DownloadViolatorsReportAdminView(SuperuserRequiredMixin, FormView):
    form_class = DownloadViolatorsReportForm
    template_name = 'download_violators.html'
    success_url = '/admin/recognition/tick/'

    def get(self, request):
        form = self.form_class(request.GET)
        if form.is_valid():
            return self.form_valid(form)
        else:
            return super().get(request)

    def form_valid(self, form):
        network = form.cleaned_data['network']
        dt_from = form.cleaned_data['dt_from']
        dt_to = form.cleaned_data['dt_to']
        exclude_created_by = form.cleaned_data['exclude_created_by']
        users = [u.id for u in form.cleaned_data['users']]
        shops = [s.id for s in form.cleaned_data['shops']]
        
        return form.get_file(network=network, dt_from=dt_from, dt_to=dt_to, exclude_created_by=exclude_created_by, user_ids=users, shop_ids=shops)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['title'] = 'Скачать отчет о нарушителях'
        context['has_permission'] = True

        return context


class ShopIpAddressViewSet(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = ShopIpAddressSerializer

    def get_object(self):
        return ShopIpAddress.objects.get(pk=self.kwargs['pk'])

    def get_queryset(self):
        shop_id = self.request.GET.get('shop_id')
        return ShopIpAddress.objects.filter(shop__id=shop_id)

    def perform_create(self, serializer):
        shop_id = self.request.data.get('shop')
        shop = Shop.objects.get(id=shop_id)
        ip_address = self.request.data.get('ip_address')
        serializer.save(shop=shop, ip_address=ip_address)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
