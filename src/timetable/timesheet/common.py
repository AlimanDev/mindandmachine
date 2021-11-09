from ..models import TimesheetItem


def _flatten_fact_timesheet_data(fact_timesheet_data):
    new_fact_timesheet_data = {}
    for empl_key, wd_data_list in fact_timesheet_data.items():
        if len(wd_data_list) == 1:
            new_fact_timesheet_data[empl_key] = wd_data_list[0]
        else:
            new_wd_data = new_fact_timesheet_data.setdefault(empl_key, {})

            # т.к. считаем, что тип в рамках 1 дня у 1 сотрудника не может различаться,
            # то берем эти данные из первого workerday
            first_wd_data = wd_data_list[0]
            new_wd_data['employee_id'] = first_wd_data['employee_id']
            new_wd_data['dt'] = first_wd_data['dt']
            new_wd_data['shop_id'] = first_wd_data['shop_id']
            new_wd_data['fact_timesheet_type_id'] = first_wd_data['fact_timesheet_type_id']
            new_wd_data['fact_timesheet_source'] = first_wd_data['fact_timesheet_source']

            # благодаря сортировке по времени можем брать время начала из первого wd, а время окончания из последнего
            if 'fact_timesheet_dttm_work_start' in first_wd_data and first_wd_data['fact_timesheet_dttm_work_start']:
                new_wd_data['fact_timesheet_dttm_work_start'] = first_wd_data['fact_timesheet_dttm_work_start']

            last_wd_data = wd_data_list[-1]
            if 'fact_timesheet_dttm_work_end' in last_wd_data and last_wd_data['fact_timesheet_dttm_work_end']:
                new_wd_data['fact_timesheet_dttm_work_end'] = last_wd_data['fact_timesheet_dttm_work_end']

            # часы для всех wd -- суммируем
            for wd_data in wd_data_list:
                if 'fact_timesheet_total_hours' in wd_data and wd_data['fact_timesheet_total_hours']:
                    new_wd_data['fact_timesheet_total_hours'] = new_wd_data.get('fact_timesheet_total_hours', 0) + \
                                                                wd_data['fact_timesheet_total_hours']
                if 'fact_timesheet_day_hours' in wd_data and wd_data['fact_timesheet_day_hours']:
                    new_wd_data['fact_timesheet_day_hours'] = new_wd_data.get('fact_timesheet_day_hours', 0) + \
                                                              wd_data['fact_timesheet_day_hours']
                if 'fact_timesheet_night_hours' in wd_data and wd_data['fact_timesheet_night_hours']:
                    new_wd_data['fact_timesheet_night_hours'] = new_wd_data.get('fact_timesheet_night_hours', 0) + \
                                                                wd_data['fact_timesheet_night_hours']

    return new_fact_timesheet_data


def _create_timesheet_items(timesheet_dict,
                            timesheet_type_key,
                            day_hours_field,
                            night_hours_field,
                            timesheet_type,
                            create_timesheet_item_cond_func=None):
    timesheet_items = []
    for timesheet_item_data_list in timesheet_dict.values():
        if isinstance(timesheet_item_data_list, dict):
            timesheet_item_data_list = [timesheet_item_data_list]
        for timesheet_item_data in timesheet_item_data_list:
            need_to_create = True
            if create_timesheet_item_cond_func:
                need_to_create = create_timesheet_item_cond_func(timesheet_item_data)

            if need_to_create:
                timesheet_items.append(TimesheetItem(
                    timesheet_type=timesheet_type,
                    employee_id=timesheet_item_data.get('employee_id'),
                    shop_id=timesheet_item_data.get('shop_id'),
                    position_id=timesheet_item_data.get('position_id'),
                    work_type_name_id=timesheet_item_data.get('work_type_name_id'),
                    dt=timesheet_item_data.get('dt'),
                    day_type_id=timesheet_item_data.get(f'{timesheet_type_key}_timesheet_type_id') or 'W',
                    dttm_work_start=timesheet_item_data.get(f'{timesheet_type_key}_timesheet_dttm_work_start'),
                    dttm_work_end=timesheet_item_data.get(f'{timesheet_type_key}_timesheet_dttm_work_end'),
                    source=timesheet_item_data.get(f'{timesheet_type_key}_timesheet_source', ''),
                    day_hours=timesheet_item_data.get(day_hours_field) or 0,
                    night_hours=timesheet_item_data.get(night_hours_field) or 0,
                ))
    TimesheetItem.objects.bulk_create(timesheet_items, batch_size=1000)
