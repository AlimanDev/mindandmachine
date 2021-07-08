from uuid import uuid4
from src.events.registry import BaseRegisteredEvent

REQUEST_APPROVE_EVENT_TYPE = 'request_approve'
APPROVE_EVENT_TYPE = 'approve'
VACANCY_CONFIRMED_TYPE = 'vacancy_confirmed'
VACANCY_CREATED = 'vacancy_created'
VACANCY_DELETED = 'vacancy_deleted'

class RequestApproveEvent(BaseRegisteredEvent):
    name = 'Запрос на подтверждение графика'
    code = REQUEST_APPROVE_EVENT_TYPE


class ApproveEvent(BaseRegisteredEvent):
    name = 'Подтверждение графика'
    code = APPROVE_EVENT_TYPE

    def get_recipients(self):
        # TODO: добавить пользователей, для которых был подтвержден график
        # TODO: подтверждаются все неподтвержденные дни периода, даже если они не отличаются от планового, что делать?
        return []

class VacancyConfirmedEvent(BaseRegisteredEvent):
    name = 'Сотрудник откликнулся на вакансию'
    code = VACANCY_CONFIRMED_TYPE

class VacancyCreatedEvent(BaseRegisteredEvent):
    name = 'Автоматически создана вакансия'
    code = VACANCY_CREATED
    write_history = True

    def get_recipients(self):
        from src.base.models import User
        return [User(id=uuid4(), email=self.context.get('director', {}).get('email'), first_name=self.context.get('director', {}).get('name', '')), ]

class VacancyDeletedEvent(BaseRegisteredEvent):
    name = 'Автоматически удалена вакансия'
    code = VACANCY_DELETED
    write_history = True

    def get_recipients(self):
        from src.base.models import User
        return [User(id=uuid4(), email=self.context.get('director', {}).get('email'), first_name=self.context.get('director', {}).get('name', '')), ]
