import distutils.util

from django.conf import settings
from django.db.models import Q, F, BooleanField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.db.models.query import Prefetch
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_yasg.utils import swagger_auto_schema
from requests.exceptions import HTTPError
from rest_auth.views import UserDetailsView
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from src.base.filters import (
    EmploymentFilter,
    BaseActiveNamedModelFilter,
    ShopScheduleFilter,
)
from src.base.filters import UserFilter, EmployeeFilter
from src.base.models import (
    ContentBlock,
    Employment,
    FunctionGroup,
    Network,
    NetworkConnect,
    ShopSettings,
    WorkerPosition,
    User,
    Group,
    Break,
    ShopSchedule,
    Employee,
)
from src.base.permissions import Permission
from src.base.serializers import (
    ContentBlockSerializer,
    EmploymentSerializer,
    UserSerializer,
    FunctionGroupSerializer,
    WorkerPositionSerializer,
    PasswordSerializer,
    ShopSettingsSerializer,
    NetworkSerializer,
    AuthUserSerializer,
    EmploymentListSerializer,
    UserListSerializer,
    GroupSerializer,
    AutoTimetableSerializer,
    BreakSerializer,
    ShopScheduleSerializer,
    EmployeeSerializer,
    EmployeeShiftScheduleQueryParamsSerializer,
)
from src.base.shift_schedule.utils import get_shift_schedule
from src.base.views_abstract import (
    BaseActiveNamedModelViewSet,
    UpdateorCreateViewSet,
    BaseModelViewSet,
)
from src.integration.models import UserExternalCode
from src.integration.zkteco import ZKTeco
from src.recognition.api.recognition import Recognition
from src.recognition.models import UserConnecter
from src.timetable.worker_day.tasks import recalc_wdays
from .filter_backends import EmployeeFilterBackend


class EmploymentViewSet(UpdateorCreateViewSet):
    """
        обязательные поля при редактировании PUT:
            position_id
            dt_hired
            dt_fired
        при создании POST дополнительно еще:
            shop_id
            user_id
        Если дата увольнения не задана, надо передать пустое поле.
    """
    permission_classes = [Permission]
    serializer_class = EmploymentSerializer
    filterset_class = EmploymentFilter
    openapi_tags = ['Employment', 'Integration',]
    queryset = Employment.objects.all()

    def perform_update(self, serializer):
        serializer.save(dttm_deleted=None)

    def get_queryset(self):
        qs = super().get_queryset().filter(
            Q(shop__network_id=self.request.user.network_id) | 
            Q(employee__user__network_id=self.request.user.network_id), # чтобы можно было аутсорсу редактировать трудоустройтсва своих сотрудников
        ).order_by('-dt_hired')
        if self.action in ['list', 'retrieve']:
            qs = qs.select_related('position', 'employee', 'employee__user', 'shop').prefetch_related(Prefetch('work_types', to_attr='work_types_list'), Prefetch('worker_constraints', to_attr='worker_constraints_list'))
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return EmploymentListSerializer
        else:
            return EmploymentSerializer

    @swagger_auto_schema(responses={200:'OK'},request_body=AutoTimetableSerializer)
    @action(detail=False, methods=['post',], serializer_class=AutoTimetableSerializer)
    def auto_timetable(self, request):
        data = AutoTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        Employment.objects.filter(id__in=data.get('employment_ids')).update(auto_timetable=data.get('auto_timetable'))
        return Response()


    @action(detail=True, methods=['put',])
    def timetable(self, request, pk=None):
        data = EmploymentSerializer(data=request.data, instance=self.get_object(), context={'request':request, 'view': self})
        data.is_valid(raise_exception=True)
        data.save()
        return Response(data.data)


class UserViewSet(UpdateorCreateViewSet):
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = UserSerializer
    filterset_class = UserFilter
    get_object_field = 'username'
    openapi_tags = ['User', 'Integration',]

    def get_queryset(self):
        user = self.request.user
        additional_networks_filter = Q(allow_assign_employements_from_outsource=True)\
            | Q(allow_choose_shop_from_client_for_employement=True)
        if self.action in ['add_biometrics', 'delete_biometrics'] and user.network.settings_values_prop.get('allow_change_outsource_biometrics', True):
            additional_networks_filter = Q()
        allowed_networks = list(NetworkConnect.objects.filter(
            additional_networks_filter,
            client_id=user.network_id,
        ).values_list('outsourcing_id', flat=True)) + [user.network_id]
        return User.objects.filter(
            network_id__in=allowed_networks,
        ).annotate(
            userconnecter_id=F('userconnecter'),
        ).distinct()

    def perform_create(self, serializer):
        if 'username' not in serializer.validated_data:
            instance = serializer.save(username=timezone.now())
            instance.username = 'user_' + str(instance.id)
            instance.save()
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        user = self.get_object()
        groups = user.get_group_ids()
        if not Group.check_has_perm_to_group(request.user, groups=groups) and user.id != request.user.id:
            raise PermissionDenied()
        serializer = PasswordSerializer(data=request.data, instance=user, context={'request':request})

        if serializer.is_valid():
            serializer.save()
            return Response()
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], parser_classes=(MultiPartParser,))
    def add_biometrics(self, *args, **kwargs):
        user = self.get_object()

        try:
            user.userconnecter
        except UserConnecter.DoesNotExist:
            if 'file' not in self.request.data:
                return Response({"detail": _('It is necessary to transfer a biometrics template (file field).')}, 400)
            biometrics_image = self.request.data['file']
            user_external_code = UserExternalCode.objects.filter(user=user).first()
            if settings.ZKTECO_INTEGRATION and user_external_code:
                ZKTeco().export_biophoto(user_external_code.code, biometrics_image)
            recognition = Recognition()
            try:
                partner_id = recognition.create_person({"id": user.id})
                recognition.upload_photo(partner_id, biometrics_image)
            except HTTPError as e:
                return Response({"detail": str(e)}, e.response.status_code)

            UserConnecter.objects.create(
                user=user,
                partner_id=partner_id,
            )
            user.avatar = biometrics_image
            user.save()
            success_msg = _('Biometrics template added successfully.')
            return Response({"detail": success_msg}, status=status.HTTP_200_OK)
        else:
            error_msg = _("The employee has biometrics. "
                          "To add a new biometrics template, you need to delete the current template.")
            return Response({"detail": error_msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def delete_biometrics(self, request, pk=None):
        user = self.get_object()
        
        try:
            user.userconnecter
        except:
            return Response({"detail": "У сотрудника нет биометрии"}, status=status.HTTP_400_BAD_REQUEST)

        recognition = Recognition()
        recognition.delete_person(user.userconnecter.partner_id)
        UserConnecter.objects.filter(user_id=user.id).delete()
        user.avatar = None
        user.save()
            
        return Response({"detail": "Биометрия сотрудника успешно удалена"}, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        else:
            return UserSerializer


class EmployeeViewSet(UpdateorCreateViewSet):
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = EmployeeSerializer
    filterset_class = EmployeeFilter
    filter_backends = [EmployeeFilterBackend]
    openapi_tags = ['Employee', ]

    def get_serializer(self, *args, **kwargs):
        if self.action == 'list':
            kwargs['user_source'] = 'employee_user'
        return super(EmployeeViewSet, self).get_serializer(*args, **kwargs)

    def get_queryset(self):
        network_filter = Q(user__network_id=self.request.user.network_id)
        # сотрудники из аутсорс сети только для чтения
        if self.action in ['list', 'retrieve']:
            outsource_networks_qs = NetworkConnect.objects.filter(
                client_id=self.request.user.network_id,
            ).values_list('outsourcing_id', flat=True)
            # рефакторинг
            other_deps_employees_with_wd_in_curr_shop = self.request.query_params.get(
                'other_deps_employees_with_wd_in_curr_shop')
            if not (other_deps_employees_with_wd_in_curr_shop and bool(
                distutils.util.strtobool(other_deps_employees_with_wd_in_curr_shop))):
                outsource_networks_qs = outsource_networks_qs.filter(allow_assign_employements_from_outsource=True)
            network_filter |= Q(
                user__network_id__in=outsource_networks_qs
            )

        qs = Employee.objects.filter(
            network_filter,
            employments__dttm_deleted__isnull=True,
        ).prefetch_related(
            Prefetch(
                'user',
                queryset=User.objects.all().annotate(
                    userconnecter_id=F('userconnecter'),
                ),
                to_attr='employee_user',
            )
        )
        return qs.distinct()

    def filter_queryset(self, queryset):
        filtered_qs = super(EmployeeViewSet, self).filter_queryset(queryset=queryset)
        include_employments = self.request.query_params.get('include_employments')
        if include_employments and bool(distutils.util.strtobool(include_employments)):
            employments_qs = Employment.objects.all().prefetch_related(Prefetch('work_types', to_attr='work_types_list')).select_related(
                'employee',
            )
            if self.request.query_params.get('shop_network__in'):
                employments_qs = employments_qs.filter(shop__network_id__in=self.request.query_params.get('shop_network__in').split(','))
            show_constraints = self.request.query_params.get('show_constraints')
            if show_constraints and bool(distutils.util.strtobool(show_constraints)):
                employments_qs = employments_qs.prefetch_related(Prefetch('worker_constraints', to_attr='worker_constraints_list'))
            filtered_qs = filtered_qs.prefetch_related(Prefetch('employments', queryset=employments_qs, to_attr='employments_list'))
        include_medical_documents = self.request.query_params.get('include_medical_documents')
        if include_medical_documents and bool(distutils.util.strtobool(include_medical_documents)):
            filtered_qs = filtered_qs.prefetch_related(
                Prefetch('medical_documents', to_attr='medical_documents_list'))
        return filtered_qs

    @action(detail=False, methods=['get'])
    def shift_schedule(self, *args, **kwargs):
        s = EmployeeShiftScheduleQueryParamsSerializer(data=self.request.query_params)
        s.is_valid(raise_exception=True)
        data = get_shift_schedule(
            network_id=self.request.user.network_id,
            employee_id=s.validated_data.get('employee_id'),
            dt__gte=s.validated_data.get('dt__gte'),
            dt__lte=s.validated_data.get('dt__lte'),
        )
        return Response(data)


class AuthUserView(UserDetailsView):
    serializer_class = AuthUserSerializer
    openapi_tags = ['Auth',]

    def check_permissions(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            rotate_token(request)
        return super().check_permissions(request, *args, **kwargs)

    def get_queryset(self):
        return User.objects.select_related('network').prefetch_related('network__outsourcings', 'network__clients').all()


class FunctionGroupView(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = FunctionGroupSerializer
    pagination_class = LimitOffsetPagination
    openapi_tags = ['FunctionGroup',]

    def get_queryset(self):
        user = self.request.user

        groups = Employment.objects.get_active(
            network_id=user.network_id,
            employee__user=user,
        ).annotate(
            group_id=Coalesce(F('function_group_id'),F('position__group_id'))
        ).values_list("group_id", flat=True)
        return FunctionGroup.objects.filter(group__in=groups).distinct('func')

    @action(detail=False, methods=['get'])
    def functions(self, request):
        return Response(FunctionGroup.FUNCS_TUPLE)


class WorkerPositionViewSet(UpdateorCreateViewSet):
    permission_classes = [Permission]
    serializer_class = WorkerPositionSerializer
    pagination_class = LimitOffsetPagination
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['WorkerPosition', 'Integration',]

    def get_queryset(self):
        include_clients = self.request.query_params.get('include_clients')
        include_outsources = self.request.query_params.get('include_outsources')
        network_filter = Q(network_id=self.request.user.network_id)
        if include_clients:
            network_filter |= Q(
                network_id__in=NetworkConnect.objects.filter(
                    outsourcing_id=self.request.user.network_id, 
                    allow_choose_shop_from_client_for_employement=True,
                ).values_list('client_id', flat=True)
            )
        if include_outsources:
            network_filter |= Q(
                network_id__in=NetworkConnect.objects.filter(
                    client_id=self.request.user.network_id, 
                ).values_list('outsourcing_id', flat=True)
            )
        now = timezone.now()
        return WorkerPosition.objects.annotate(
            is_active=ExpressionWrapper(
                Q(dttm_deleted__isnull=True) | 
                Q(dttm_deleted__gte=now),
                output_field=BooleanField(),
            )
        ).filter(
            network_filter,
        )

class ShopSettingsViewSet(BaseActiveNamedModelViewSet):
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = ShopSettingsSerializer
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['ShopSettings',]

    def get_queryset(self):
        user = self.request.user
        return ShopSettings.objects.filter(
            network_id=user.network_id
        )


class NetworkViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = NetworkSerializer
    queryset = Network.objects.all()
    openapi_tags = ['Network',]


class GroupViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = GroupSerializer
    pagination_class = LimitOffsetPagination
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['Group',]
    
    def get_queryset(self):
        return Group.objects.filter(
            network_id=self.request.user.network_id,
        )


class BreakViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [Permission]
    serializer_class = BreakSerializer
    filterset_class = BaseActiveNamedModelFilter
    openapi_tags = ['Break',]

    def get_queryset(self):
        return Break.objects.filter(
            network_id=self.request.user.network_id,
        )


class ShopScheduleViewSet(UpdateorCreateViewSet):
    permission_classes = [Permission]
    serializer_class = ShopScheduleSerializer
    filterset_class = ShopScheduleFilter
    openapi_tags = ['ShopSchedule',]

    lookup_field = 'dt'
    lookup_url_kwarg = 'dt'

    def get_queryset(self):
        return ShopSchedule.objects.filter(
            shop_id=self.kwargs.get('department_pk'), shop__network_id=self.request.user.network_id)

    def _perform_create_or_update(self, serializer):
        serializer.save(
            modified_by=self.request.user,
            shop_id=self.kwargs.get('department_pk'),
            dt=self.kwargs.get('dt'),
        )
        recalc_wdays.delay(
            shop_id=self.kwargs.get('department_pk'),
            dt__gte=self.kwargs.get('dt'),
            dt__lte=self.kwargs.get('dt'),
        )

    def perform_create(self, serializer):
        self._perform_create_or_update(serializer)

    def perform_update(self, serializer):
        self._perform_create_or_update(serializer)


class ContentBlockViewSet(ReadOnlyModelViewSet):
    serializer_class = ContentBlockSerializer
    permission_classes = [Permission]

    def get_queryset(self):
        filters = {
            'network_id': self.request.user.network_id
        }
        if self.request.query_params.get('code'):
            filters['code'] = self.request.query_params.get('code')
        
        return ContentBlock.objects.filter(**filters)
