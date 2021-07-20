from src.events.registry import BaseRegisteredEvent

from datetime import date, timedelta, datetime


URV_STAT = 'urv_stat'
URV_STAT_TODAY = 'urv_stat_today'
URV_VIOLATORS_REPORT = 'urv_violators_report'
URV_STAT_V2 = 'urv_stat_v2'

class URVReportEventMixin:
    @staticmethod
    def get_dates(context):
        dt_from = context.get('dt_from')
        dt_to = context.get('dt_to')
        if not dt_from or not dt_to:
            dt_from = dt_to = date.today() - timedelta(1)
        else:
            dt_from = datetime.strptime(dt_from, '%Y-%m-%d').date()
            dt_to = datetime.strptime(dt_to, '%Y-%m-%d').date()
        return dt_from, dt_to

class UrvStatEvent(BaseRegisteredEvent, URVReportEventMixin):
    name = 'Отправка отчета по УРВ'
    code = URV_STAT
    write_history = False

    def get_file(self):
        from src.reports.utils.create_urv_stat import urv_stat_v1
        dt_from, dt_to = self.get_dates(self.context)
        title = f'URV_{dt_from}-{dt_to}.xlsx'
        return urv_stat_v1(dt_from, dt_to, title=title, shop_ids=self.context.get('shop_ids', []), network_id=self.network_id, in_memory=True)
        

class UrvStatTodayEvent(BaseRegisteredEvent):
    name = 'Отправка отчета по УРВ за сегодняшний день'
    code = URV_STAT_TODAY
    write_history = False

    def get_file(self):
        from src.reports.utils.create_urv_stat import urv_stat_v1
        dt = date.today()
        title = f'URV_today_{dt}.xlsx'

        return urv_stat_v1(dt, dt, title=title, shop_ids=self.context.get('shop_ids', []), network_id=self.network_id, comming_only=True, in_memory=True)

class UrvViolatorsReportEvent(BaseRegisteredEvent, URVReportEventMixin):
    name = 'Отправка отчета по нарушителям УРВ'
    code = URV_VIOLATORS_REPORT
    write_history = False

    def get_file(self):
        from src.reports.utils.urv_violators import urv_violators_report_xlsx
        dt_from, dt_to = self.get_dates(self.context)

        return urv_violators_report_xlsx(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', []), in_memory=True)


class UrvStatV2Event(BaseRegisteredEvent, URVReportEventMixin):
    name = 'Отправка отчета по УРВ версия 2'
    code = URV_STAT_V2
    write_history = False

    def get_file(self):
        from src.reports.utils.create_urv_stat import urv_stat_v2
        dt_from, dt_to = self.get_dates(self.context)
        title = f'URV_users_{dt_from}-{dt_to}.xlsx'

        return urv_stat_v2(dt_from, dt_to, title=title, network_id=self.network_id, shop_ids=self.context.get('shop_ids', []), in_memory=True)
