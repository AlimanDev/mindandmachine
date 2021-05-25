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
            'Операция не может быть выполнена. Нарушены ограничения по запланированным задачам. ({task_violation_str})').format(
            task_violation_str=task_violation_str
        )
