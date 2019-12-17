from django.db.models import F
from src.base.models import (
    Shop,
)
from src.timetable.models import (
    WorkType,
    WorkerDay,
    WorkerDayCashboxDetails,
)
from src.util.models_converter import (
    WorkerDayConverter,
    BaseConverter,
    UserConverter,
    VacancyConverter,
)
from .forms import (
    GetWorkersToExchange,
    NotifyWorkersAboutVacancyForm,
    ShowVacanciesForm,
    VacancyForm,
)
from .utils import (
    search_candidates,
    send_noti2candidates,
    cancel_vacancy as cancel_vacancy_util,
)
from src.util.utils import api_method, JsonResponse
from django.utils import timezone


@api_method(
    'GET',
    GetWorkersToExchange,
    lambda_func=lambda x: WorkType.objects.get(id=x['specialization']).shop
)
def get_workers_to_exchange(request, form):
    """
    Note:
        Для работы биржы смен необходимы права ALL
        на функции get_workers_to_exchange, get_cashier_timetable, get_month_stat
    # todo: fix this
    Args:
        method: GET
        url: /api/timetable/worker_exchange/get_workers_to_exchange
        specialization(int): required = True. на какую специализацию ищем замену
        dttm_start(QOS_DATETIME): required = True. на какую дату-время ищем замену
        dttm_end(QOS_DATETIME): required = True. на какую дату-время ищем замену

    Returns:
        {
            'users':[
                user_id: {
                    | 'info': dict with User info
                    | 'timetable': list of dict WorkerDay models  -- расписание работы сотрудника в интервале [-10, 10] \
                     дней от запрашиваемого для замены
                }
            ]
            'tt_from_dt': дата, с которой отрисовывать расписание
            'tt_to_dt': дата, по которую отрисовывать расписание

    """

    work_type = WorkType.objects.select_related(
        'shop', 'shop__parent').get(id=form['specialization'], dttm_deleted__isnull=True)
    worker_day = WorkerDayCashboxDetails(
        dttm_from=form['dttm_start'],
        dttm_to=form['dttm_end'],
        work_type=work_type,
    )

    search_params = {
        'outsource': True if form['outsource'] else False,
    }

    workers = search_candidates(worker_day, **search_params)  # fixme: may return tooooo much users
    # workers = workers.prefetch_related('employments')
    # workers = workers.annotate(
    #     parent_title=F('shop__parent__title'),
    #     shop_title=F('shop__title')
    # )  # fixme: delete this -- specially for current front

    users = {}
    for worker in workers:
        worker_info = UserConverter.convert_main(worker)
        # worker_info['shop_title'] = list(worker.employments.all().values_list('shop__title', flat=True))
        # worker_info['supershop_title'] = worker.parent_title
        users[worker.id] = {'info': worker_info, 'timetable': []}

    change_dt = form['dttm_start'].date()
    worker_days = list(WorkerDay.objects.qos_current_version().filter(
        worker_id__in=users.keys(),
        dt__gte=change_dt - timezone.timedelta(days=10),
        dt__lte=change_dt + timezone.timedelta(days=10),
    ).order_by('worker_id', 'dt')) # fixme: ordering just for frontend

    for wd in worker_days:
        users[wd.worker_id]['timetable'].append(WorkerDayConverter.convert(wd))

    res_dict = {
        'users': users,
        'tt_from_dt': BaseConverter.convert_date(change_dt - timezone.timedelta(days=10)),
        'tt_to_dt': BaseConverter.convert_date(change_dt + timezone.timedelta(days=10)),
    }
    return JsonResponse.success(res_dict)


@api_method(
    'POST',
    NotifyWorkersAboutVacancyForm,
    lambda_func=lambda x: WorkType.objects.get(id=x['work_type']).shop
)
def notify_workers_about_vacancy(request, form):
    """
    Рассылаем уведомление сотрудникам о вакансии и создаем вакансию
    method: POST
    url: /api/timetable/worker_exchange/notify_workers_about_vacancy
    Args:
        work_type(int): required = True. на какую специализацию ищем замену
        dttm_start(QOS_DATETIME): required = True. на какую дату-время ищем замену
        dttm_end(QOS_DATETIME): required = True. на какую дату-время ищем замену

        worker_ids: список сотрудников, кому отправляем уведомление
    Returns:
        {}
    """
    work_type = WorkType.objects.get(id=form['work_type'],dttm_deleted__isnull=True)
    worker_day_detail = WorkerDayCashboxDetails.objects.create(
        dttm_from=form['dttm_start'],
        dttm_to=form['dttm_end'],
        work_type=work_type,
        status=WorkerDayCashboxDetails.TYPE_VACANCY,
        is_vacancy=True,
    )
    worker_day_detail.work_type = work_type

    # for checking permissions
    search_params = {
        'outsource': True,
    }
    workers = search_candidates(worker_day_detail, **search_params)
    users = workers.filter(id__in=form['worker_ids'])

    send_noti2candidates(users, worker_day_detail)
    return JsonResponse.success()


@api_method(
    'GET',
    ShowVacanciesForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def show_vacancy(request, form):
    """
    Отображает список вакансии по определенному департаменту
    method: GET
    url: /api/timetable/worker_exchange/show_vacancy
    Args:
        shop_id(int): required = True. по какому департаменту смотрим
        pointer(int): required = False. смещение(какую страницу) смотрим
        count(int): required = False. сколько максимум отображать объектов на странице

        worker_ids: список сотрудников, кому отправляем уведомление
    Returns:
        {
            'vacancies': список вакансий Vacancy [
               | 'id': int,
               | 'dttm_added': datetime,
               | 'dt': date,
               | 'dttm_from': datetime,
               | 'dttm_to': datetime,
               | 'worker_fio': str -- фио сотрудника,
               | 'is_canceled': bool,
               | 'work_type': идентификатор работ,
            ],
        }
    """

    pointer = form['pointer'] if form['pointer'] else 0
    count = form['count'] if form['count'] else 30

    vacancies = WorkerDayCashboxDetails.objects.filter(
        work_type__shop=form['shop_id'],
        is_vacancy=True,
    ).select_related('worker_day', 'worker_day__worker').order_by('-id')[pointer * count: (pointer + 1) * count]

    res_dict = {
        'vacancies': [VacancyConverter.convert(vac) for vac in vacancies],
    }
    return JsonResponse.success(res_dict)


@api_method(
    'POST',
    VacancyForm,
    lambda_func=lambda x: Shop.objects.get(worktype__workerdaycashboxdetails__id=x['vacancy_id'])
)
def cancel_vacancy(request, form):
    """
    удаляет размещенную вакансию

    method: POST
    url: /api/timetable/worker_exchange/cancel_vacancy
    Args:
        vacancy_id(int): required = True. идентификатор вакансии
    Returns:
        {}

    """
    cancel_vacancy_util(form['vacancy_id'])
    return JsonResponse.success()
