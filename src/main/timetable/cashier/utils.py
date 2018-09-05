from src.db.models import WorkerDay


def prepare_worker_day_create_args(form, worker):
    args = {
        'worker_id': worker.id,
        'dt': form['dt'],
        'type': form['type'],
        'is_manual_tuning': True,
    }

    if WorkerDay.is_type_with_tm_range(form['type']):
        args.update({
            'dttm_work_start': form['dttm_work_start'],
            'dttm_work_end': form['dttm_work_end'],
            'tm_break_start': form['tm_break_start']
        })
    else:
        args.update({
            'dttm_work_start': None,
            'dttm_work_end': None,
            'tm_break_start': None
        })

    return args


def worker_day_create_args(form):
    wd_args = {
        'dt': form['dt'],
        'type': form['type'],
    }
    if WorkerDay.is_type_with_tm_range(form['type']):
        wd_args.update({
            'dttm_work_start': form['dttm_work_start'],
            'dttm_work_end': form['dttm_work_end'],
            'tm_break_start': form['tm_break_start']
        })
    else:
        wd_args.update({
            'dttm_work_start': None,
            'dttm_work_end': None,
            'tm_break_start': None
        })
    return wd_args


def prepare_worker_day_change_create_args(request, form, day):
    args = {
        'worker_day_id': day.id,

        'worker_day_dt': form['dt'],
        'worker_day_worker_id': form['worker_id'],

        'from_type': day.type,
        'to_type': form['type'],

        'changed_by_id': request.user.id,
        'comment': form['comment']
    }

    if WorkerDay.is_type_with_tm_range(day.type):
        args.update({
            'from_dttm_work_start': day.dttm_work_start,
            'from_dttm_work_end': day.dttm_work_end,
            'from_dttm_break_start': day.tm_break_start
        })
    if WorkerDay.is_type_with_tm_range(form['type']):
        args.update({
            'to_dttm_work_start': form['dttm_work_start'],
            'to_dttm_work_end': form['dttm_work_end'],
            'to_dttm_break_start': form['tm_break_start']
        })

    return args
