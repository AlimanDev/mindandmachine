from src.adapters.celery.celery import app
from src.apps.exchange.tasks import run_import_job
from src.apps.forecast.receipt.tasks import aggregate_timeserie_value, clean_timeserie_actions
from src.apps.exchange.models import ImportJob

from django.conf import settings
from celery import chain

import logging
from typing import List, Optional, Union
import datetime

ONE_DAY_DELTA = datetime.timedelta(days=1)
logger = logging.getLogger('etl')



def get_load_tasks(
    import_job_ids,
    date_from: Union[datetime.date, str],
    date_to: Union[datetime.date, str],
):
    if isinstance(date_from, str):
        date_from = datetime.datetime.strptime(date_from, settings.QOS_DATE_FORMAT).date()
    if isinstance(date_to, str):
        date_to = datetime.datetime.strptime(date_to, settings.QOS_DATE_FORMAT)
    
    logger.info(f'start mport data from {date_from} to {date_to}')
    logger.info(f'import for indecies {import_job_ids}')
    return chain(
        run_import_job.si(
            import_job_id=i_j_id,
            date_from=date_from.strftime(settings.QOS_DATE_FORMAT),
            date_to=date_to.strftime(settings.QOS_DATE_FORMAT),
        )
        for i_j_id in import_job_ids
    ) 


@app.task()
def import_aggregate_delete_receipts(
    import_job_ids: List[int],
    dt_from: Union[str, datetime.date] = datetime.date.today(),
    dt_to: Union[str, datetime.date] = datetime.date.today(),
    date_gap_ahead: int = settings.DEFAULT_RECEIPTS_GAP_AHEAD,
    date_gap_before: int = settings.DEFAULT_RECEIPTS_GAP_BEFORE,
    delete_data_from: Optional[Union[str, datetime.date, int]] = None,
) -> None:
    """To import aggregate delete receipts data
    
    Args:
        import_job_ids (List[int]): list of import job ids to proceed
        dt_from (Union[str, datetime.date], optional): date since proceed, inclusive. Defaults to datetime.date.today().
        dt_to (Union[str, datetime.date], optional): date until proceed, inclusive. Defaults to datetime.date.today().
        date_gap_ahead (int, optional): Number of days to fetch ahead. Some times data source provides data on previous date in prepared files. 
            Thus to import data on day X we need to check some files ahead. Defaults to 3.
        date_gap_before (int, optional): As mentioned before data source on day X provides also data on X-1, X-2 days.
            So when new data arrives to system there is also data on previous dates, so update may be needed. Defaults to 3.
        delete_data_from: (Union[str, datetime.date, int], optional). 
            To keep fetched receipts. Just wont allow to delete receipts before.
            If string it will be parsed according to `dt_format`. If None set to `dt_to`. 
            If int it will be `delete_data_from` before `dt_to`.
            Defaults to `dt_to`.

    Example:
        # 1
        if one need to re import-aggregate corrupted data on previous dates [X->Y] this the case
        define import ids for which produce aggregation
        We also need to fetch data on next days, eg 4 to receive pieces of data delivered by customer with lag
        We also dont delete imported data, for e.g. 3 days for further usage by periodic tasks
        import_aggregate_delete_receipts(
            import_job_ids=ids,
            dt_from=X,
            dt_to=Y,
            date_gap_before=0,
            date_gap_ahead=4,
            delete_data_from=3,
        )
        The process deletes data from storage, in this case [-inf, Y+4]
        Then data is written and deleted day-wise
        Aggregation wont be applied anywhere but [X->Y]
        After task completion all receipts before Y-3days will be delete.
        In this case from [Y-3, Y+4] will be left in storage if it was empty before
    """
    
    timedelta_gap_ahead = ONE_DAY_DELTA * date_gap_ahead
    timedelta_gap_before = ONE_DAY_DELTA * date_gap_before

    if isinstance(dt_from, str):
        dt_from=datetime.datetime.strptime(dt_from, settings.QOS_DATE_FORMAT).date()

    if isinstance(dt_to, str):
        dt_to=datetime.datetime.strptime(dt_to, settings.QOS_DATE_FORMAT).date()

    if delete_data_from is None:
        delete_data_from = dt_to
    elif isinstance(delete_data_from, str):
        delete_data_from = datetime.datetime.strptime(
            delete_data_from, settings.QOS_DATE_FORMAT
        ).date()
    elif isinstance(delete_data_from, int):
        delete_data_from = dt_to - ONE_DAY_DELTA * delete_data_from

    # get data types to process delete and aggregation
    jobs = ImportJob.objects.filter(
        id__in=import_job_ids
    ).prefetch_related('import_strategy').all()
    d_types = (
        j.import_strategy.data_type for j in jobs
        if hasattr(j.import_strategy, 'data_type')
    )
    data_types_to_process = list(set(d_types))
    logger.info(f'process following data types: {data_types_to_process}')

    dttm_to_delete = datetime.datetime.combine(
        date=dt_to + timedelta_gap_ahead, time=datetime.time.max
    )
    logger.info(f'start delete for {dttm_to_delete.strftime(settings.QOS_DATE_FORMAT)}')
    tasks = chain(
        clean_timeserie_actions.si(
            dttm_for_delete=dttm_to_delete.strftime(settings.QOS_DATETIME_FORMAT),
            data_types_to_process=data_types_to_process
        )
    )

    dt_from -= timedelta_gap_before
    load_to = dt_from + timedelta_gap_ahead
    # pre load data
    load_from = dt_from
    tasks = tasks | get_load_tasks(
            import_job_ids=import_job_ids,
            date_from=load_from.strftime(settings.QOS_DATE_FORMAT),
            date_to=load_to.strftime(settings.QOS_DATE_FORMAT),
        )
    load_date = load_to
    agg_date = load_from
    delta_d = (dt_to - dt_from).days
    # next load one day more, aggregate, delete one day and so on
    for d_offset in range(delta_d+1):
        # load
        if d_offset != 0:
            tasks = tasks | chain(
                get_load_tasks(
                    import_job_ids=import_job_ids,
                    date_from=load_date.strftime(settings.QOS_DATE_FORMAT),
                    date_to=load_date.strftime(settings.QOS_DATE_FORMAT),
                )
            )
        # aggregate
        logger.info(f'start aggregate for {agg_date}')
        tasks = tasks | aggregate_timeserie_value.si(
            agg_date.strftime(settings.QOS_DATE_FORMAT), 
            update_tail=0,
            data_types_to_process=data_types_to_process
        )


        # delete what was aggregated
        dttm_to_delete = datetime.datetime.combine(
            date=min(agg_date, delete_data_from), time=datetime.time.max
        )
        logger.info(f'start delete for {dttm_to_delete}')
        tasks = tasks | clean_timeserie_actions.si(
            dttm_for_delete=dttm_to_delete.strftime(settings.QOS_DATETIME_FORMAT),
            data_types_to_process=data_types_to_process
        )

        # increment date to process values
        load_date += ONE_DAY_DELTA
        agg_date += ONE_DAY_DELTA

    # as mentioned to aggregate data on day X we must also fetch data on days 
    # X+1, X+2, X+gap_ahead
    # due to clients that sends us delayed checks and deliveries
    # so basicly here we delete all data fetched ahead
    dttm_to_delete = datetime.datetime.combine(
            date=min(load_date, delete_data_from), time=datetime.time.max
        )
    logger.info(f'start delete for {dttm_to_delete.strftime(settings.QOS_DATE_FORMAT)}')
    tasks = tasks | clean_timeserie_actions.si(
        dttm_for_delete=dttm_to_delete.strftime(settings.QOS_DATETIME_FORMAT),
        data_types_to_process=data_types_to_process,
    )
    tasks()
