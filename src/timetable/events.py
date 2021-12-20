from uuid import uuid4
from src.events.registry import BaseRegisteredEvent

REQUEST_APPROVE_EVENT_TYPE = 'request_approve'
APPROVE_EVENT_TYPE = 'approve'
VACANCY_CONFIRMED_TYPE = 'vacancy_confirmed'
VACANCY_RECONFIRMED_TYPE = 'vacancy_reconfirmed'
VACANCY_CREATED = 'vacancy_created'
VACANCY_DELETED = 'vacancy_deleted'
VACANCY_REFUSED = 'vacancy_refused'
EMPLOYEE_VACANCY_DELETED = 'employee_vacancy_deleted'

class RequestApproveEvent(BaseRegisteredEvent):
    name = 'Запрос на подтверждение графика'
    code = REQUEST_APPROVE_EVENT_TYPE


class ApproveEvent(BaseRegisteredEvent):
    name = 'Подтверждение графика'
    code = APPROVE_EVENT_TYPE

    def get_recipients(self):
        # TODO: добавить пользователей, для которых был подтвержден график
        return []


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
        from src.base.models import User
        return list(User.objects.filter(id=self.context.get('user_id')))


class VacancyReconfirmedEvent(BaseRegisteredEvent):
    name = 'Сотрудник переназначен на вакансию'
    code = VACANCY_RECONFIRMED_TYPE
    write_history = True


class VacancyRefusedEvent(BaseRegisteredEvent):
    name = 'Отмена назначения сотрудника на вакансию'
    code = VACANCY_REFUSED
    write_history = True
