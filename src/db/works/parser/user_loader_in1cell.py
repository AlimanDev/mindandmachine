import pandas
import datetime
from src.db.models import User, WorkerDay


def in1cell_loader(path, sheet_name, shop, first_day, st_row, end_row, st_col, end_col, fio_col=4):
    st_row  -= 3
    end_row -= 2
    st_col  -= 1
    fio_col -= 1
    # end_col -= 1

    tm_format = '%H:%M'

    types = {
        'В': WorkerDay.Type.TYPE_HOLIDAY.value,
        'ОТ': WorkerDay.Type.TYPE_VACATION.value,
    }

    data = pandas.read_excel(path, sheet_name=sheet_name).values

    for row in range(st_row, end_row):
        fio = data[row, fio_col].split()
        try:
            user = User.objects.get(last_name=fio[0], first_name=fio[1], middle_name=fio[2], shop=shop)
        except User.DoesNotExist:
            user = None

        if user:
            days = []
            for i, col in enumerate(range(st_col, end_col)):
                val = data[row, col]
                if val in types.keys():
                    tp = types[val]
                    st_tm = None
                    end_tm = None
                else:
                    tp = WorkerDay.Type.TYPE_WORKDAY.value
                    st_tm, end_tm = [datetime.datetime.strptime(tm, tm_format).time() for tm in val.split('-')]
                days.append(WorkerDay(
                    type=tp,
                    dt=first_day + datetime.timedelta(days=i),
                    worker=user,

                    tm_work_start=st_tm,
                    tm_work_end=end_tm,

                    worker_shop=shop, # fuck you!
                ))
            WorkerDay.objects.bulk_create(days)
        else:
            print('no user with fio {}'.format(fio))
