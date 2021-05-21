from src.events.registry import BaseRegisteredEvent

REQUEST_APPROVE_EVENT_TYPE = 'request_approve'
APPROVE_EVENT_TYPE = 'approve'
VACANCY_CONFIRMED_TYPE = 'vacancy_confirmed'


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
