import datetime
from django.utils.translation import gettext_lazy as _

from src.apps.timetable.work_type.utils import ShopEfficiencyGetter


class TimetableService:
    def get_header(self, shop_id: int, start_date: datetime.date, end_date: datetime.date):
        raw_response = ShopEfficiencyGetter(shop_id, start_date, end_date, graph_type='plan_edit').get()
        res = {'efficiency_metrics': [], 'days': []}
        day_stats = raw_response['day_stats']
        for date in day_stats['covering'].keys():
            date_stat = {
                key: day_stats[key][date] for key in day_stats.keys()
            }
            date_stat['date'] = date
            res['efficiency_metrics'].append(date_stat)

        dates = [start_date + datetime.timedelta(days=day) for day in range((end_date - start_date + datetime.timedelta(1)).days)]

        for date in dates:
            res['days'].append({'date': date, 'day_name': _(f'{date:%a}')})

        return res
