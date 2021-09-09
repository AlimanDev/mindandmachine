import io

import xlsxwriter
from admin_numeric_filter.admin import RangeNumericFilter
from django.contrib import admin
from django.contrib.auth.models import Group
from django.db.models import Prefetch, Min, Q
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.timezone import now
from django_admin_listfilter_dropdown.filters import RelatedOnlyDropdownFilter
from rangefilter.filter import DateTimeRangeFilter

from src.recognition.models import TickPoint, Tick, TickPhoto, UserConnecter
from src.timetable.models import User, Employment
from src.util.dg.ticks_report import TicksOdsReportGenerator, TicksOdtReportGenerator

admin.site.unregister(Group)


class RelatedOnlyDropdownNameOrderedFilter(RelatedOnlyDropdownFilter):
    def field_choices(self, field, request, model_admin):
        pk_qs = model_admin.get_queryset(request).distinct().values_list('%s__pk' % self.field_path, flat=True)
        return field.get_choices(include_blank=False, limit_choices_to={'pk__in': pk_qs}, ordering=['name',])


class UserListFilter(admin.SimpleListFilter):
    title = 'User'
    parameter_name = 'user__id__exact'
    related_filter_parameter = 'tick_point__shop__id__exact'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
            in the right sidebar.
        """
        list_of_questions = []
        queryset = User.objects.order_by('last_name', 'first_name')
        if self.related_filter_parameter in request.GET:
            dt = now().date()
            e = Employment.objects.get_active(request.user.network_id, dt, dt, shop_id=request.GET[self.related_filter_parameter]).values_list(
                'employee__user_id')
            queryset = queryset.filter(id__in=e)
        for user in queryset:
            list_of_questions.append(
                (str(user.id), "{}, {}".format(user.first_name, user.last_name))
            )
        return sorted(list_of_questions, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value to decide how to filter the queryset.
        if self.parameter_name in request.GET:
            user_id = request.GET[self.parameter_name]
            if user_id:
                return queryset.filter(user__id=user_id)
        return queryset


class PhotoUserListFilter(UserListFilter):
    parameter_name = 'tick__user__id__exact'
    related_filter_parameter = 'tick__tick_point__shop__id__exact'

    def queryset(self, request, queryset):
        if self.parameter_name in request.GET:
            user_id = request.GET[self.parameter_name]
            if user_id:
                return queryset.filter(tick__user__id=user_id)
        return queryset


class TickMinLivenessFilter(RangeNumericFilter):
    title = 'Min liveness'
    parameter_name = 'min_liveness'

    def queryset(self, request, queryset):
        queryset = queryset.annotate(
            min_liveness=Coalesce(Min('tickphoto__liveness', filter=Q(tickphoto__liveness__gt=0)), 0),
        )
        return super(TickMinLivenessFilter, self).queryset(request, queryset)


@admin.register(Tick)
class TickAdmin(admin.ModelAdmin):
    raw_id_fields = ("user", "tick_point", 'employee')
    list_display = [
        'id',
        'type',
        'dttm',
        'verified_score',
        'min_liveness_prop',
        'image_tag_self',
        'image_tag_first',
        'image_tag_last',
        'user',
        'tick_point',
    ]

    list_filter = [
        ('tickphoto__liveness', TickMinLivenessFilter),
        ('tick_point__shop', RelatedOnlyDropdownNameOrderedFilter),
        ('dttm', DateTimeRangeFilter),
        'type',
        UserListFilter,
    ]

    actions = ['download_old', 'ticks_report_xlsx', 'ticks_report_docx']
    change_list_template = 'ticks_change_list.html'
    list_select_related = (
        'user',
        'tick_point'
    )

    def get_queryset(self, request):
        return super(TickAdmin, self).get_queryset(request).prefetch_related(
            Prefetch(
                'tickphoto_set',
                queryset=TickPhoto.objects.filter(),
                to_attr='tickphotos_list',
            )
        )

    def ticks_report_xlsx(self, request, queryset):
        generator = TicksOdsReportGenerator(ticks_queryset=queryset)
        content = generator.generate(convert_to='xlsx')
        response = HttpResponse(content, content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename="ticks_report.xlsx"'
        return response

    def ticks_report_docx(self, request, queryset):
        generator = TicksOdtReportGenerator(ticks_queryset=queryset)
        content = generator.generate(convert_to='docx')
        response = HttpResponse(content, content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename="ticks_report.docx"'
        return response

    # aa: fixme: remove, not working
    def download_old(self, request, queryset):
        def set_tick(dict, tick):
            if tick.type not in dict \
                    or (tick.type == Tick.TYPE_COMING and tick.dttm < dict[tick.type].dttm) \
                    or (tick.type == Tick.TYPE_LEAVING and tick.dttm > dict[tick.type].dttm):
                dict[tick.type] = tick

        format = "%Y-%m-%d %H:%M:%S"
        output = io.BytesIO()

        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        format_meta_bold = workbook.add_format({'font_size': 11,
                                                'bold': True})
        worksheet = workbook.add_worksheet('Timestamp')
        worksheet.write_row(
            'A1',
            ['shop_name',
             'shop_code',
             'employee_name',
             'employee_tabel',
             'StartTimestamp',
             'FinalTimestamp',
             ], format_meta_bold)

        dt_ticks = {}
        for tick in queryset:
            if not (tick.type == Tick.TYPE_COMING or tick.type == Tick.TYPE_LEAVING):
                continue

            dt = tick.dttm.date()
            if dt not in dt_ticks:
                dt_ticks[dt] = {}
            if tick.user_id not in dt_ticks[dt]:
                dt_ticks[dt][tick.user_id] = {}
            set_tick(dt_ticks[dt][tick.user_id], tick)
        index = 0
        for dt in dt_ticks.keys():
            for user_id in dt_ticks[dt].keys():
                index += 1
                tick_c = dt_ticks[dt][user_id].get(Tick.TYPE_COMING)
                tick_l = dt_ticks[dt][user_id].get(Tick.TYPE_LEAVING)
                tick = tick_c if tick_c else tick_l
                worksheet.write_row(
                    index, 0,
                    [tick.tick_point.shop.name,
                     tick.tick_point.shop.code,
                     "{} {} {}".format(
                         tick.user.last_name,
                         tick.user.first_name,
                         tick.user.middle_name),
                     tick.user.tabel_code,
                     tick_c.dttm.strftime(format) if tick_c else '',
                     tick_l.dttm.strftime(format) if tick_l else '',
                     ]
                )

        workbook.close()
        output.seek(0)
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="urv.xlsx"'

        return response


@admin.register(TickPhoto)
class TickPhotoAdmin(admin.ModelAdmin):
    raw_id_fields = ("tick",)

    list_filter = [('liveness', RangeNumericFilter),
                   ('dttm', DateTimeRangeFilter),
                   'type',
                   ('tick__tick_point__shop', RelatedOnlyDropdownFilter),
                   PhotoUserListFilter,
                   ]
    list_display = ['id', 'user', 'type', 'tick_point', 'liveness', 'verified_score', 'dttm', 'image_tag']
    readonly_fields = ['image_tag', 'tick']
    save_as = True

    def user(self, obj):
        return obj.tick.user

    def tick_point(self, obj):
        return obj.tick.tick_point

    def lookup_allowed(self, key, value):
        return True

    def image_tag(self, obj):
        return format_html('<a href="{0}"> <img src="{0}", height="150" /></a>'.format(obj.image.url))

    image_tag.short_description = 'Image'


@admin.register(TickPoint)
class TickPointAdmin(admin.ModelAdmin):
    list_filter = ['shop']
    list_display = ['id', 'name', 'shop', 'dttm_added', 'is_active']


@admin.register(UserConnecter)
class UserConnecterAdmin(admin.ModelAdmin):
    search_fields = ['user__last_name', 'user__first_name', 'user__id', 'user__username', 'partner_id']
    list_filter = ['user']
    list_display = ['partner_id', 'user']
