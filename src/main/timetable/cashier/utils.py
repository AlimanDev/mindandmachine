from src.db.models import WorkerDay


def prepare_worker_day_create_args(form, worker):
    args = {
        'worker_id': worker.id,
        'worker_shop_id': worker.shop_id,
        'dt': form['dt'],
        'type': form['type'],
        'is_manual_tuning': True
    }

    if form['type'] == WorkerDay.Type.TYPE_WORKDAY.value:
        args.update({
            'tm_work_start': form['tm_work_start'],
            'tm_work_end': form['tm_work_start'],
            'tm_break_start': form['tm_break_start']
        })
    else:
        args.update({
            'tm_work_start': None,
            'tm_work_end': None,
            'tm_break_start': None
        })

    return args


def prepare_worker_day_update_obj(form, day):
    day.type = form['type']
    day.is_manual_tuning = True

    if form['type'] == WorkerDay.Type.TYPE_WORKDAY.value:
        day.tm_work_start = form['tm_work_start']
        day.tm_work_end = form['tm_work_end']
        day.tm_break_start = form['tm_break_start']
    else:
        day.tm_work_start = None
        day.tm_work_end = None
        day.tm_break_start = None


def prepare_worker_day_change_create_args(request, form, day):
    args = {
        'worker_day_id': day.id,

        'worker_day_dt': form['dt'],
        'worker_day_worker_id': form['worker_id'],

        'from_type': day.type,
        'to_type': form['type'],

        'changed_by_id': request.user.id
    }

    if day.type == WorkerDay.Type.TYPE_WORKDAY.value:
        args.update({
            'from_tm_work_start': day.tm_work_start,
            'from_tm_work_end': day.tm_work_end,
            'from_tm_break_start': day.tm_break_start
        })
    if form['type'] == WorkerDay.Type.TYPE_WORKDAY.value:
        args.update({
            'to_tm_work_start': form['tm_work_start'],
            'to_tm_work_end': form['tm_work_end'],
            'to_tm_break_start': form['tm_break_start']
        })

    return args
