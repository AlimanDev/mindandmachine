from django.utils.translation import gettext


class WorkTimeOverlap(Exception):
    def __init__(self, overlaps):
        self.overlaps = overlaps

    def __str__(self, *args, **kwargs):
        overlaps_str = ', '.join(
            f'{overlap["employee__user__last_name"]} {overlap["employee__user__first_name"]} - {overlap["dt"]}'
            for overlap in self.overlaps
        )
        return gettext('The operation cannot be performed. Unacceptable intersection of working hours. ({overlaps_str})').format(
            overlaps_str=overlaps_str
        )


class WorkDayTaskViolation(Exception):
    def __init__(self, task_violations):
        self.task_violations = task_violations

    def __str__(self, *args, **kwargs):
        # TODO: перевести
        task_violation_str = ', '.join(
            f'{task_violation["employee__user__last_name"]} {task_violation["employee__user__first_name"]}: {task_violation["dt"]}. Минимальный необходимый интервал работы: {task_violation["task_least_start_time"].strftime("%H:%M")}-{task_violation["task_greatest_end_time"].strftime("%H:%M")}. Текущий интервал: {task_violation["dttm_work_start"].strftime("%H:%M") if task_violation["dttm_work_start"] else None}-{task_violation["dttm_work_end"].strftime("%H:%M") if task_violation["dttm_work_end"] else None}'
            for task_violation in self.task_violations
        )
        return gettext(
            'The operation cannot be performed. Restrictions on scheduled tasks have been violated. ({task_violation_str})').format(
            task_violation_str=task_violation_str
        )


class MultipleWDTypesOnOneDateForOneEmployee(Exception):
    def __init__(self, multiple_workday_types_data):
        self.multiple_workday_types_data = multiple_workday_types_data

    def __str__(self, *args, **kwargs):
        error_str = ', '.join(
            f'{error_data["employee__user__last_name"]} {error_data["employee__user__first_name"]} - {error_data["dt"]}'
            for error_data in self.multiple_workday_types_data
        )
        return gettext(
                'The operation cannot be performed. '
                'The restrictions on the allowed types of days on one date for one employee have been violated.. ({error_str})').format(
            error_str=error_str
        )


class HasAnotherWdayOnDate(Exception):
    def __init__(self, exc_data):  # TODO: рефакторинг, сделать базовый exception для транзакционных проверок wd
        self.exc_data = exc_data

    def __str__(self, *args, **kwargs):
        error_str = ', '.join(
            f'{error_data["employee__user__last_name"]} {error_data["employee__user__first_name"]} - {error_data["dt"]}'
            for error_data in self.exc_data
        )
        return gettext(
                'The operation cannot be performed. '
                'Creating multiple days on the same date for one employee is prohibited. ({error_str})').format(
            error_str=error_str
        )


class MainWorkHoursGreaterThanNorm(Exception):
    def __init__(self, exc_data):
        self.exc_data = exc_data

    def __str__(self, *args, **kwargs):
        error_str = ', '.join(
            (
                f'{error_data["last_name"]} {error_data["first_name"]} - '
                f'С {error_data["dt_from"]} по {error_data["dt_to"]} норма: {error_data["norm"]}, в графике: {error_data["total_work_hours"]}'
            )
            for error_data in self.exc_data
        )
        return gettext(
                'The operation cannot be performed. '
                'The restrictions on the number of hours in the main schedule have been violated.. ({error_str})').format(
            error_str=error_str
        )


class DtMaxHoursRestrictionViolated(Exception):
    def __init__(self, exc_data):
        self.exc_data = exc_data

    def __str__(self, *args, **kwargs):
        error_str = ', '.join(
            (
                f'{error_data["last_name"]} {error_data["first_name"]} - '
                f'{error_data["worker_day_type"] or ""} {error_data["dt"]} текущее значение {error_data["current_work_hours"]}, разрешено не более {error_data["dt_max_hours"]}'
            )
            for error_data in self.exc_data
        )
        return gettext(
                'Операция не может быть выполнена. '
                'Нарушены ограничения по максимальному количеству часов. ({error_str})').format(
            error_str=error_str
        )
