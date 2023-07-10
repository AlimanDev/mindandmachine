from src.apps.events.registry import BaseRegisteredEvent
from django.utils.translation import gettext_lazy as _


REQUEST_APPROVE_EVENT_TYPE = 'request_approve'
REQUEST_APPROVE_WITH_TASKS_EVENT_TYPE = 'request_approve_with_tasks'
APPROVE_EVENT_TYPE = 'approve'
APPROVED_NOT_FIRST_EVENT = 'approved_not_first'
VACANCY_CONFIRMED_TYPE = 'vacancy_confirmed'
VACANCY_RECONFIRMED_TYPE = 'vacancy_reconfirmed'
VACANCY_CREATED = 'vacancy_created'
VACANCY_DELETED = 'vacancy_deleted'
VACANCY_REFUSED = 'vacancy_refused'
EMPLOYEE_VACANCY_DELETED = 'employee_vacancy_deleted'


class RequestApproveEvent(BaseRegisteredEvent):
    name = 'Запрос на подтверждение графика'
    code = REQUEST_APPROVE_EVENT_TYPE

class RequestApproveWithTasksEvent(BaseRegisteredEvent):
    """
    Request approve of draft timetable and new days have tasks violations.
    Example: a Task assigned to Employee at 10:00, but new WorkerDay changes dttm_work_start from 09:00 to 11:00.
    The Task now falls outside the day, which is a violation, and would require a special approval.
    """
    name = _('Request approved with tasks')
    code = REQUEST_APPROVE_WITH_TASKS_EVENT_TYPE

class ApproveEvent(BaseRegisteredEvent):
    name = 'Подтверждение графика'
    code = APPROVE_EVENT_TYPE

    def get_recipients(self):
        # TODO: добавить пользователей, для которых был подтвержден график
        return []


class ApprovedNotFirstEvent(BaseRegisteredEvent):
    """Orteka-specific"""
    name = _('Worker days approved not first (have a parent day)')
    code = APPROVED_NOT_FIRST_EVENT
    write_history = False


class VacancyConfirmedEvent(BaseRegisteredEvent):
    name = 'Сотрудник откликнулся на вакансию'
    code = VACANCY_CONFIRMED_TYPE
    write_history = True


class VacancyCreatedEvent(BaseRegisteredEvent):
    name = 'Создана вакансия'
    code = VACANCY_CREATED
    write_history = True


class VacancyDeletedEvent(BaseRegisteredEvent):
    name = 'Удалена вакансия'
    code = VACANCY_DELETED
    write_history = True


class VacancyEmployeeDeletedEvent(BaseRegisteredEvent):
    name = 'Удалена вакансия для сотрудника'
    code = EMPLOYEE_VACANCY_DELETED
    write_history = True

    def get_recipients(self):
        from src.apps.base.models import User
        return list(User.objects.filter(id=self.context.get('user_id')))


class VacancyReconfirmedEvent(BaseRegisteredEvent):
    name = 'Сотрудник переназначен на вакансию'
    code = VACANCY_RECONFIRMED_TYPE
    write_history = True


class VacancyRefusedEvent(BaseRegisteredEvent):
    name = 'Отмена назначения сотрудника на вакансию'
    code = VACANCY_REFUSED
    write_history = True
