import json
import urllib.parse

from dateutil.parser import parse
from diff_match_patch import diff_match_patch
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
from django.contrib.admin.utils import unquote, flatten_fieldsets
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.forms import Form
from django.forms.formsets import all_valid
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse, resolve
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from import_export import resources
from import_export.admin import ExportActionMixin, ImportMixin
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget
from mptt.exceptions import InvalidMove
from sesame.utils import get_token

from src.base.admin_filters import CustomChoiceDropdownFilter, RelatedOnlyDropdownLastNameOrderedFilter, \
    RelatedOnlyDropdownNameOrderedFilter
from src.base.forms import (
    CustomConfirmImportShopForm,
    CustomImportShopForm,
    FunctionGroupAdminForm,
    NetworkAdminForm,
    ShopAdminForm,
    ShopSettingsAdminForm,
    BreakAdminForm,
    CustomImportFunctionGroupForm,
    CustomConfirmImportFunctionGroupForm,
    SawhSettingsAdminForm,
    SawhSettingsMappingAdminForm,
)
from src.base.models import (
    Employment,
    User,
    Shop,
    ShopSettings,
    Group,
    FunctionGroup,
    WorkerPosition,
    Region,
    ProductionDay,
    Network,
    Break,
    SAWHSettings,
    SAWHSettingsMapping,
    ShopSchedule,
    Employee,
    NetworkConnect,
    ApiLog,
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftScheduleInterval,
    ContentBlock,
    AllowedSawhSetting,
)
from src.base.shop.utils import get_offset_timezone_dict, get_shop_name
from src.timetable.models import GroupWorkerDayPermission


class BaseNotWrapRelatedModelaAdmin(admin.ModelAdmin):
    not_wrap_fields = [] # only foreign key fields

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in self.not_wrap_fields and isinstance(db_field, models.ForeignKey):
            return self.formfield_for_foreignkey(db_field, request, **kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


class FunctionGroupResource(resources.ModelResource):
    group = Field(attribute='group_id')

    class Meta:
        model = FunctionGroup
        import_id_fields = ('func', 'method', 'group',)
        fields = ('func', 'method', 'access_type', 'level_up', 'level_down',)

    def get_export_fields(self):
        return [self.fields[f] for f in self.Meta.fields]

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        data = dataset.dict
        for row in data:
            row['access_type'] = row['access_type'] or ''
        new_data = []
        for gid in kwargs.get('groups', []):
            for row in data:
                row = row.copy()
                row['group'] = gid
                new_data.append(row)
        dataset.dict = new_data


class ShopResource(resources.ModelResource):
    parent = Field(attribute='parent_id')
    parent_name = Field(
        attribute='parent',
        column_name='Parent Name',
        widget=ForeignKeyWidget(Shop, 'name'),
        readonly=True,
    )

    class Meta:
        model = Shop
        import_id_fields = ('name',)
        fields = ('name', 'parent', 'tm_open_dict', 'tm_close_dict', 'timezone')

    def get_import_fields(self):
        return [self.fields[f] for f in self.Meta.fields]
    
    def get_export_fields(self):
        return [self.fields[f] for f in self.Meta.fields]

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        network = kwargs.get('network', None)
        shops = Shop.objects.all()
        tz_info = get_offset_timezone_dict()
        if network:
            shops = shops.filter(network_id=network)
        shops_dict = {s.name: s.id for s in shops}
        shops = list(shops_dict.keys())
        data = dataset.dict
        for row in data:
            tm_open, tm_close = row['times'].split('-')
            row['name_in_file'] = row['name']
            row['name'] = get_shop_name(row['name'], shops)
            row['parent_name_in_file'] = row['parent']
            row['parent_name'] = get_shop_name(row['parent'], shops)
            row['parent'] = shops_dict.get(row['parent_name'])
            row['timezone'] = tz_info.get(float(row['timezone'].split()[-1]), 'Europe/Moscow')
            row['tm_open_dict'] = json.dumps({'all': parse(tm_open).strftime('%H:%M:%S')})
            row['tm_close_dict'] = json.dumps({'all': parse(tm_close).strftime('%H:%M:%S')})
        dataset.dict = data

    def after_import_row(self, row, row_result, row_number=None, **kwargs):
        row_result.diff.insert(2, row['parent_name_in_file'])
        dmp = diff_match_patch()
        diff = dmp.diff_main(row['name_in_file'], row['name'])
        dmp.diff_cleanupSemantic(diff)
        html = dmp.diff_prettyHtml(diff)
        html = mark_safe(html)
        row_result.diff.insert(4, html)

    def get_diff_headers(self):
        headers = super().get_diff_headers()
        headers.insert(2, 'parent in file')
        headers.insert(4, 'name in file')
        return headers


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'logo')
    form = NetworkAdminForm
    fieldsets = (
        (_('Basic settings'), {'fields': ('logo', 'url', 'primary_color', 'secondary_color', 'name', 'code', 'okpo')}),
        (_('Time attendance settings'), {
            'fields': (
                'allowed_interval_for_late_arrival',
                'allowed_interval_for_early_departure',
                'allowed_geo_distance_km',
                'enable_camera_ticks',
                'max_work_shift_seconds',
                'skip_leaving_tick',
                'max_plan_diff_in_seconds',
                'trust_tick_request',
            )
        }),
        (_('Time tracking settings'), {
            'fields': (
                'crop_work_hours_by_shop_schedule',
                'accounting_period_length',
                'only_fact_hours_that_in_approved_plan',
                'prev_months_work_hours_source',
                'fines_settings',
                'round_work_hours_alg',
            ),
        }),
        (_('Vacancy settings'), {
            'fields': (
                'need_symbol_for_vacancy',
                'use_internal_exchange',
                'allow_workers_confirm_outsource_vacancy',
                'show_cost_for_inner_vacancies',
            )
        }),
        (_('Format settings'), {'fields': (
            'download_tabel_template',
            'convert_tabel_to',
            'timetable_format',
            'add_users_from_excel',
            'show_checkbox_for_inspection_version',

        )}),
        (_('Timetable settings'), {'fields': (
            'show_worker_day_additional_info',
            'show_worker_day_tasks',
            'copy_plan_to_fact_crossing',
        )}),
        (_('Timesheet settings'), {'fields': (
            'consider_remaining_hours_in_prev_months_when_calc_norm_hours',
            'correct_norm_hours_last_month_acc_period',
            'get_position_from_work_type_name_in_calc_timesheet',
            'fiscal_sheet_divider_alias',
            'timesheet_max_hours_threshold',
            'timesheet_min_hours_threshold',
            'timesheet_divider_sawh_hours_key',
        )}),
        (_('Integration settings'), {'fields': (
            'api_timesheet_lines_group_by',
            'descrease_employment_dt_fired_in_api',
            'ignore_parent_code_when_updating_department_via_api',
            'ignore_shop_code_when_updating_employment_via_api',
            'create_employment_on_set_or_update_director_code',
        )}),
        (_('Default settings'), {'fields': ('breaks', 'load_template', 'exchange_settings', 'worker_position_default_values', 'shop_default_values')}),
        (_('Other'), {'fields': (
            'settings_values',
            'show_user_biometrics_block',
            'forbid_edit_employments_came_through_integration',
            'allow_creation_several_wdays_for_one_employee_for_one_date',
            'run_recalc_fact_from_att_records_on_plan_approve',
            'edit_manual_fact_on_recalc_fact_from_att_records',
            'set_closest_plan_approved_delta_for_manual_fact',
            'clean_wdays_on_employment_dt_change',
            'rebuild_timetable_min_delta',
            'analytics_type',
        )}),
    )


@admin.register(NetworkConnect)
class NetworkConnectAdmin(admin.ModelAdmin):
    list_display = ('id', 'outsourcing', 'client')
    list_select_related = ('outsourcing', 'client')


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'parent')
    list_filter = ('parent',)


class WorkerPositionAdminForm(forms.ModelForm):
    class Meta:
        model = WorkerPosition
        fields = '__all__'

    allowed_sawh_settings = forms.ModelMultipleChoiceField(
        queryset=SAWHSettings.objects.none(),
        label='Разрешенные настройки нормы',
        required=False,
        blank=True,
        widget=FilteredSelectMultiple(
            verbose_name=SAWHSettings._meta.verbose_name,
            is_stacked=False,
        ),
    )

    def __init__(self, *args, **kwargs):
        super(WorkerPositionAdminForm, self).__init__(*args, **kwargs)
        if self.instance:
            self.fields['allowed_sawh_settings'].queryset = SAWHSettings.objects.filter(
                network_id=self.instance.network_id).select_related('network')
            self.fields['allowed_sawh_settings'].initial = SAWHSettings.objects.filter(
                id__in=AllowedSawhSetting.objects.filter(
                    position=self.instance).values_list('sawh_settings_id', flat=True)
            ).select_related('network')

    def save(self, *args, **kwargs):
        instance = super(WorkerPositionAdminForm, self).save(*args, **kwargs)
        with transaction.atomic():
            AllowedSawhSetting.objects.filter(position=self.instance).delete()
            AllowedSawhSetting.objects.bulk_create(
                [
                    AllowedSawhSetting(position=self.instance, sawh_settings=sawh_settings)
                    for sawh_settings in self.cleaned_data['allowed_sawh_settings']
                ]
            )

        return instance


@admin.register(WorkerPosition)
class WorkerPositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')
    search_fields = ('name', 'code')
    list_filter = ('network',)
    form = WorkerPositionAdminForm


class QsUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User


class AdmimGenerateOTPAuthLinkForm(forms.Form):
    """
    Пустая форма для создания временной ссылки для входа под конкретным пользователем
    """
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, **kwargs):
        return settings.EXTERNAL_HOST + reverse('auth:one_time_pass') + '?' + urllib.parse.urlencode(
            {settings.SESAME_TOKEN_NAME: get_token(self.user)})


@admin.register(User)
class QsUserAdmin(UserAdmin):
    list_display = ('first_name', 'last_name', 'shop_name', 'id', 'username',)
    search_fields = ('first_name', 'last_name', 'id', 'username',)
    readonly_fields = ('dttm_added',)
    form = QsUserChangeForm
    fieldsets = (
        (None, {'fields': ('username', 'password', 'auth_type')}),
        (_('Personal info'), {'fields': ('last_name', 'first_name', 'middle_name', 'birthday', 'sex', 'email', 'phone_number', 'lang', 'avatar')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined', 'dttm_added', 'dttm_deleted')}),
        (_('Other'), {'fields': (
            'network',
            'code',
            'access_token',
            'black_list_symbol',
        )}),
    )
    generate_otp_auth_link_form = AdmimGenerateOTPAuthLinkForm
    generate_otp_auth_link_template = 'generate_otp_auth_link.html'
    change_form_template = 'user_change_form.html'

    def get_urls(self):
        return [
            path(
                '<_id>/generate_otp_auth_link/',
                self.admin_site.admin_view(self.user_generate_otp_auth_link),
                name='generate_otp_auth_link',
            ),
        ] + super().get_urls()

    def user_generate_otp_auth_link(self, request, _id, form_url=''):
        user = self.get_object(request, unquote(_id))
        if not self.has_change_permission(request, user):
            raise PermissionDenied
        if user is None:
            raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % {
                'name': self.model._meta.verbose_name,
                'key': escape(_id),
            })
        if request.method == 'POST':
            form = self.generate_otp_auth_link_form(user, request.POST)
            if form.is_valid():
                otp_auth_link = form.save()
                msg = mark_safe(f'<a href="{otp_auth_link}">Ссылка</a> успешно сгенерирована')
                messages.success(request, msg)
                return HttpResponseRedirect(
                    reverse(
                        '%s:%s_%s_change' % (
                            self.admin_site.name,
                            user._meta.app_label,
                            user._meta.model_name,
                        ),
                        args=(user.pk,),
                    )
                )
        else:
            form = self.generate_otp_auth_link_form(user)

        fieldsets = [(None, {'fields': list(form.base_fields)})]
        adminForm = admin.helpers.AdminForm(form, fieldsets, {})

        context = {
            'title': 'Сгенерировать одноразовую ссылку для входа: %s' % escape(user.get_username()),
            'adminForm': adminForm,
            'form_url': form_url,
            'form': form,
            'is_popup': (IS_POPUP_VAR in request.POST or
                         IS_POPUP_VAR in request.GET),
            'add': True,
            'change': False,
            'has_delete_permission': False,
            'has_change_permission': True,
            'has_absolute_url': False,
            'opts': self.model._meta,
            'original': user,
            'save_as': False,
            'show_save': True,
            **self.admin_site.each_context(request),
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(
            request,
            self.generate_otp_auth_link_template,
            context,
        )

    @staticmethod
    def shop_name(instance: User):
        res = ', '.join(
            list(
                Employment.objects.get_active(employee__user=instance).values_list('shop__name', flat=True).distinct()))
        return res

    '''
    @staticmethod
    def work_type_name(instance: User):
        cashboxinfo_set = instance.workercashboxinfo_set.all().select_related('work_type')
        return ' '.join(['"{}"'.format(cbi.work_type.name) for cbi in cashboxinfo_set])
    '''


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'tabel_code')
    search_fields = ('id', 'user__last_name', 'user__first_name', 'user__username', 'tabel_code')
    raw_id_fields = ('user',)


@admin.register(Shop)
class ShopAdmin(ImportMixin, admin.ModelAdmin):
    list_display = ('name', 'parent_title', 'id', 'code')
    search_fields = ('name', 'parent__name', 'id', 'code')
    raw_id_fields = ('director',)
    form = ShopAdminForm
    resource_class = ShopResource

    @staticmethod
    def parent_title(instance: Shop):
        return instance.parent_title()
    
    def get_import_form(self):
        return CustomImportShopForm

    def get_confirm_import_form(self):
        return CustomConfirmImportShopForm

    def get_deleted_objects(self, *args, **kwargs):
        with Shop._deletion_context():
            return super().get_deleted_objects(*args, **kwargs)

    def get_form_kwargs(self, form, *args, **kwargs):
        if isinstance(form, Form) and form.is_valid():
            network = form.cleaned_data['network']
            kwargs.update({'network': getattr(network, 'id', None)})
        return kwargs

    def get_import_data_kwargs(self, request, *args, **kwargs):
        form = kwargs.get('form')
        if form and form.is_valid():
            network = form.cleaned_data['network']
            kwargs.update({'network': getattr(network, 'id', None)})
        return super().get_import_data_kwargs(request, *args, **kwargs)

    def _changeform_view(self, request, object_id, form_url, extra_context):
        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField("The field %s cannot be referenced." % to_field)

        model = self.model
        opts = model._meta

        if request.method == 'POST' and '_saveasnew' in request.POST:
            object_id = None

        add = object_id is None

        if add:
            if not self.has_add_permission(request):
                raise PermissionDenied
            obj = None

        else:
            obj = self.get_object(request, unquote(object_id), to_field)

            if request.method == 'POST':
                if not self.has_change_permission(request, obj):
                    raise PermissionDenied
            else:
                if not self.has_view_or_change_permission(request, obj):
                    raise PermissionDenied

            if obj is None:
                return self._get_obj_does_not_exist_redirect(request, opts, object_id)

        fieldsets = self.get_fieldsets(request, obj)
        ModelForm = self.get_form(
            request, obj, change=not add, fields=flatten_fieldsets(fieldsets)
        )
        if request.method == 'POST':
            form = ModelForm(request.POST, request.FILES, instance=obj)
            form_validated = form.is_valid()
            if form_validated:
                new_object = self.save_form(request, form, change=not add)
            else:
                new_object = form.instance
            formsets, inline_instances = self._create_formsets(request, new_object, change=not add)
            if all_valid(formsets) and form_validated:
                try:
                    self.save_model(request, new_object, form, not add)
                except InvalidMove as e:
                    form.add_error('parent', str(e))
                    form_validated = False
                if form_validated:
                    self.save_related(request, form, formsets, not add)
                    change_message = self.construct_change_message(request, form, formsets, add)
                    if add:
                        self.log_addition(request, new_object, change_message)
                        return self.response_add(request, new_object)
                    else:
                        self.log_change(request, new_object, change_message)
                        return self.response_change(request, new_object)
            else:
                form_validated = False
        else:
            if add:
                initial = self.get_changeform_initial_data(request)
                form = ModelForm(initial=initial)
                formsets, inline_instances = self._create_formsets(request, form.instance, change=False)
            else:
                form = ModelForm(instance=obj)
                formsets, inline_instances = self._create_formsets(request, obj, change=True)

        if not add and not self.has_change_permission(request, obj):
            readonly_fields = flatten_fieldsets(fieldsets)
        else:
            readonly_fields = self.get_readonly_fields(request, obj)
        adminForm = helpers.AdminForm(
            form,
            list(fieldsets),
            # Clear prepopulated fields on a view-only form to avoid a crash.
            self.get_prepopulated_fields(request, obj) if add or self.has_change_permission(request, obj) else {},
            readonly_fields,
            model_admin=self)
        media = self.media + adminForm.media

        inline_formsets = self.get_inline_formsets(request, formsets, inline_instances, obj)
        for inline_formset in inline_formsets:
            media = media + inline_formset.media

        if add:
            title = _('Add %s')
        elif self.has_change_permission(request, obj):
            title = _('Change %s')
        else:
            title = _('View %s')
        context = {
            **self.admin_site.each_context(request),
            'title': title % opts.verbose_name,
            'subtitle': str(obj) if obj else None,
            'adminform': adminForm,
            'object_id': object_id,
            'original': obj,
            'is_popup': IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET,
            'to_field': to_field,
            'media': media,
            'inline_admin_formsets': inline_formsets,
            'errors': helpers.AdminErrorList(form, formsets),
            'preserved_filters': self.get_preserved_filters(request),
        }

        # Hide the "Save" and "Save and continue" buttons if "Save as New" was
        # previously chosen to prevent the interface from getting confusing.
        if request.method == 'POST' and not form_validated and "_saveasnew" in request.POST:
            context['show_save'] = False
            context['show_save_and_continue'] = False
            # Use the change template instead of the add template.
            add = False

        context.update(extra_context or {})

        return self.render_change_form(request, context, add=add, change=not add, obj=obj, form_url=form_url)

    def get_import_form(self):
        return CustomImportShopForm

    def get_confirm_import_form(self):
        return CustomConfirmImportShopForm

    def get_form_kwargs(self, form, *args, **kwargs):
        if isinstance(form, Form) and form.is_valid():
            network = form.cleaned_data['network']
            kwargs.update({'network': getattr(network, 'id', None)})
        return kwargs

    def get_import_data_kwargs(self, request, *args, **kwargs):
        form = kwargs.get('form')
        if form and form.is_valid():
            network = form.cleaned_data['network']
            kwargs.update({'network': getattr(network, 'id', None)})
        return super().get_import_data_kwargs(request, *args, **kwargs)


@admin.register(ShopSettings)
class ShopSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('id', 'name')
    form = ShopSettingsAdminForm


class GroupWorkerDayPermissionInline(admin.TabularInline):
    model = GroupWorkerDayPermission
    extra = 0

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('group', 'worker_day_permission')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'network',)
    list_filter = ('network',)
    search_fields = ('name', 'code',)
    save_as = True

    def save_model(self, request, obj, form, change):
        obj.save()
        # Django always sends this when "Save as new is clicked"
        if '_saveasnew' in request.POST:
            # Get the ID from the admin URL
            original_pk = resolve(request.path).kwargs['object_id']
            funcs = FunctionGroup.objects.filter(group_id=original_pk)
            FunctionGroup.objects.bulk_create(
                [
                    FunctionGroup(
                        group=obj,
                        func=f.func,
                        method=f.method,
                        access_type=f.access_type,
                        level_down=f.level_down,
                        level_up=f.level_up,
                    )
                    for f in funcs
                ]
            )
            from src.timetable.models import GroupWorkerDayPermission
            gwdps = GroupWorkerDayPermission.objects.filter(group_id=original_pk)
            GroupWorkerDayPermission.objects.bulk_create(
                [
                    GroupWorkerDayPermission(
                        group=obj,
                        worker_day_permission=gwdp.worker_day_permission,
                        limit_days_in_past=gwdp.limit_days_in_past,
                        limit_days_in_future=gwdp.limit_days_in_future,
                    )
                    for gwdp in gwdps
                ]
            )


@admin.register(FunctionGroup)
class FunctionGroupAdmin(ImportMixin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'access_type', 'group', 'func', 'method', 'level_down', 'level_up')
    list_filter = [
        ('group', RelatedOnlyDropdownNameOrderedFilter),
        ('func', CustomChoiceDropdownFilter),
    ]
    # list_filter = ('access_type', 'group', 'func')
    list_select_related = ('group',)
    search_fields = ('id',)
    resource_class = FunctionGroupResource
    form = FunctionGroupAdminForm

    def get_import_form(self):
        return CustomImportFunctionGroupForm

    def get_confirm_import_form(self):
        return CustomConfirmImportFunctionGroupForm

    def get_form_kwargs(self, form, *args, **kwargs):
        if isinstance(form, Form) and form.is_valid():
            groups = form.cleaned_data['groups']
            kwargs.update({'groups': groups.values_list('id', flat=True)})
        return kwargs

    def get_import_data_kwargs(self, request, *args, **kwargs):
        form = kwargs.get('form')
        if form and form.is_valid():
            groups = form.cleaned_data['groups']
            kwargs.update({'groups': groups.values_list('id', flat=True)})
        return super().get_import_data_kwargs(request, *args, **kwargs)


@admin.register(Employment)
class EmploymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'employee', 'function_group', 'dt_hired_formated', 'dt_fired_formated')
    list_select_related = ('employee', 'employee__user', 'shop', 'shop__parent', 'function_group')
    list_filter = [
        ('shop', RelatedOnlyDropdownNameOrderedFilter),
    ]
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 'shop__name', 'shop__parent__name',
                     'employee__tabel_code')
    raw_id_fields = ('shop', 'employee', 'position')

    def dt_hired_formated(self, obj):
        return obj.dt_hired.strftime('%d.%m.%Y') if obj.dt_hired else '-'

    dt_hired_formated.short_description = 'dt hired'

    def dt_fired_formated(self, obj):
        return obj.dt_fired.strftime('%d.%m.%Y') if obj.dt_fired else '-'

    dt_fired_formated.short_description = 'dt fired'


@admin.register(ProductionDay)
class ProductionDayAdmin(admin.ModelAdmin):
    list_display = ('dt', 'type', 'is_celebration', 'region')
    list_filter = ('region', 'type', 'is_celebration')


@admin.register(Break)
class BreakAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')
    search_fields = ('name',)
    form = BreakAdminForm


class SAWHSettingsMappingInline(admin.TabularInline):
    model = SAWHSettingsMapping
    extra = 0
    form = SawhSettingsMappingAdminForm


class SAWHSettingsAdminForm(SawhSettingsAdminForm):
    class Meta:
        model = SAWHSettings
        fields = '__all__'

    positions = forms.ModelMultipleChoiceField(
        queryset=WorkerPosition.objects.none(),
        label='Должности',
        required=False,
        blank=True,
        widget=FilteredSelectMultiple(
            verbose_name=WorkerPosition._meta.verbose_name,
            is_stacked=False,
        )
    )

    def __init__(self, *args, **kwargs):
        super(SAWHSettingsAdminForm, self).__init__(*args, **kwargs)
        if self.instance and self.instance.id:
            self.fields['positions'].queryset = WorkerPosition.objects.filter(
                network_id=self.instance.network_id)
            self.fields['positions'].initial = self.instance.positions.all()

    def save(self, *args, **kwargs):
        instance = super(SAWHSettingsAdminForm, self).save(*args, **kwargs)
        with transaction.atomic():
            if instance.id:
                self.fields['positions'].initial.update(sawh_settings=None)
                self.cleaned_data['positions'].update(sawh_settings=instance)
        return instance


@admin.register(SAWHSettings)
class SAWHSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'code',
        'type',
    )
    save_as = True
    inlines = (
        SAWHSettingsMappingInline,
    )
    form = SAWHSettingsAdminForm


@admin.register(ShopSchedule)
class ShopScheduleAdmin(admin.ModelAdmin):
    raw_id_fields = ('shop',)
    list_filter = ('dt', 'shop',)
    list_display = ('dt', 'shop', 'modified_by', 'type', 'opens', 'closes')
    readonly_fields = ('modified_by',)

    def save_model(self, request, obj, form, change):
        obj.modified_by = request.user
        obj.save(recalc_wdays=True)


@admin.register(ApiLog)
class ApiLogAdmin(admin.ModelAdmin):
    list_display = (
        'view_func',
        'http_method',
        'url_kwargs',
        'request_datetime',
        'user',
        'response_ms',
        'response_status_code',
    )
    list_filter = (
        'view_func',
        'http_method',
        ('user', RelatedOnlyDropdownLastNameOrderedFilter),
        'response_status_code',
    )
    search_fields = ('url_kwargs', 'request_data')
    raw_id_fields = ('user',)
    list_select_related = ('user',)


@admin.register(ShiftSchedule)
class ShiftScheduleAdmin(admin.ModelAdmin):
    raw_id_fields = ('network', 'employee')
    list_filter = ('employee', 'network',)
    list_display = ('id', 'name', 'code', 'employee')
    save_as = True


@admin.register(ShiftScheduleDay)
class ShiftScheduleDayAdmin(admin.ModelAdmin):
    raw_id_fields = ('shift_schedule',)
    list_filter = ('dt', 'shift_schedule', 'day_type')
    list_display = ('id', 'shift_schedule', 'dt', 'code', 'day_type', 'work_hours')
    save_as = True


@admin.register(ShiftScheduleInterval)
class ShiftScheduleIntervalAdmin(admin.ModelAdmin):
    raw_id_fields = ('shift_schedule', 'employee')
    list_filter = (
        ('shift_schedule', RelatedOnlyDropdownNameOrderedFilter),
        ('employee__user', RelatedOnlyDropdownLastNameOrderedFilter),
    )
    list_display = ('id', 'shift_schedule', 'employee', 'dt_start', 'dt_end', 'code',)
    save_as = True

@admin.register(ContentBlock)
class ContentBlockAdmin(admin.ModelAdmin):
    list_display = ('network', 'code', 'name',)
    list_select_related = ('network',)
    search_fields = ('code', 'name', 'network__name',)
    list_filter = (
        ('network', RelatedOnlyDropdownNameOrderedFilter),
    )


@admin.register(AllowedSawhSetting)
class AllowedSawhSettingAdmin(admin.ModelAdmin):
    list_display = ('position', 'sawh_settings', )
    search_fields = (
        'position_id',
        'sawh_settings_id',
        'position__name',
        'position__code',
        'sawh_settings__name',
        'sawh_settings__code',
    )
    list_filter = (
        ('position', RelatedOnlyDropdownNameOrderedFilter),
        ('sawh_settings', RelatedOnlyDropdownNameOrderedFilter),
    )
