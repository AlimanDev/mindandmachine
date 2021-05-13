from django.utils.translation import gettext


class WorkTimeOverlap(Exception):
    def __init__(self, overlaps):
        self.overlaps = overlaps

    def __str__(self, *args, **kwargs):
        overlaps_str = ', '.join(
            f'{overlap["employee__user__last_name"]} {overlap["employee__user__first_name"]} - {overlap["dt"]}'
            for overlap in self.overlaps
        )
        return gettext('Операция не может быть выполнена. Недопустимое пересечение времени работы. ({overlaps_str})').format(
            overlaps_str=overlaps_str
        )
