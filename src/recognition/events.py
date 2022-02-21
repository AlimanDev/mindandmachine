from src.events.registry import BaseRegisteredEvent

from uuid import uuid4

EMPLOYEE_NOT_CHECKED_IN = 'employee_not_checked_in'
EMPLOYEE_NOT_CHECKED_OUT = 'employee_not_checked_out'
EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN = 'employee_working_not_according_to_plan'
DUPLICATE_BIOMETRICS = 'duplicate_biometrics'


class EmployeeNotCheckedInEvent(BaseRegisteredEvent):
    name = 'Сотрудник не отметился на приход.'
    code = EMPLOYEE_NOT_CHECKED_IN
    write_history = True


class EmployeeNotCheckedOutEvent(BaseRegisteredEvent):
    name = 'Сотрудник не отметился на уход.'
    code = EMPLOYEE_NOT_CHECKED_OUT
    write_history = True


class EmployeeWorkingNotAccordingToPlanEvent(BaseRegisteredEvent):
    name = 'Сотрудник вышел не по плану'
    code = EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN
    write_history = False


class DuplicateBiometricsEvent(BaseRegisteredEvent):
    name = 'Обнаружен дубликат биометрических параметров'
    code = DUPLICATE_BIOMETRICS
    write_history = True
