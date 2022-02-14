import datetime
from src.celery.celery import app
from src.timetable.vacancy.utils import (
    create_vacancies_and_notify,
    cancel_vacancies,
    workers_exchange,
)
from src.timetable.models import ExchangeSettings, WorkType
from src.base.models import Shop


@app.task
def vacancies_create_and_cancel():
    """
    Создание вакансий для всех магазинов
    """

    exchange_settings_network = {
        e.network_id: e
        for e in ExchangeSettings.objects.filter(shops__isnull=True)
    }

    for shop in Shop.objects.select_related('exchange_settings').all():
        exchange_settings = shop.exchange_settings or exchange_settings_network.get(shop.network_id)
        if exchange_settings == None or not (exchange_settings.automatic_create_vacancies or exchange_settings.automatic_delete_vacancies):
            continue

        vacancies_create_and_cancel_for_shop(shop.id)


@app.task
def vacancies_create_and_cancel_for_shop(shop_id):
    """
    Создание вакансий для всех магазинов
    """

    for work_type in WorkType.objects.qos_filter_active(datetime.date.today(), datetime.date.today(), shop_id=shop_id):
        cancel_vacancies(shop_id, work_type.id, approved=True)
        create_vacancies_and_notify(shop_id, work_type.id)


@app.task
def create_shop_vacancies_and_notify(shop_id, work_type_id):
    """
    Создание вакансий для магазина
    """

    create_vacancies_and_notify(shop_id, work_type_id)


@app.task
def cancel_shop_vacancies(shop_id, work_type_id):
    """
    Автоматически отменяем вакансии, в которых нет потребности
    :return:
    """
    cancel_vacancies(shop_id, work_type_id)


@app.task
def workers_hard_exchange():
    """
    Автоматически перекидываем сотрудников из других магазинов, если
    в том магазине потребность в сотруднике < 20%.

    :return:
    """
    workers_exchange()
