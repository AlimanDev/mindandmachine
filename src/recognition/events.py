from src.events.registry import BaseRegisteredEvent

from datetime import date, timedelta


URV_STAT = 'urv_stat'
URV_STAT_TODAY = 'urv_stat_today'
URV_VIOLATORS_REPORT = 'urv_violators_report'
URV_STAT_V2 = 'urv_stat_v2'


class UrvStatEvent(BaseRegisteredEvent):
    name = 'Отправка отчета по УРВ за вчерашний день'
    code = URV_STAT
    write_history = False

    def get_file(self):
        from src.util.urv.create_urv_stat import urv_stat_v1
        dt = date.today() - timedelta(days=1)
        title = f'URV_{dt}.xlsx'

        return urv_stat_v1(dt, dt, title=title, network_id=self.network_id, in_memory=True)
        

class UrvStatTodayEvent(BaseRegisteredEvent):
    name = 'Отправка отчета по УРВ за сегодняшний день'
    code = URV_STAT_TODAY
    write_history = False

    def get_file(self):
        from src.util.urv.create_urv_stat import urv_stat_v1
        dt = date.today()
        title = f'URV_today_{dt}.xlsx'

        return urv_stat_v1(dt, dt, title=title, network_id=self.network_id, comming_only=True, in_memory=True)

class UrvViolatorsReportEvent(BaseRegisteredEvent):
    name = 'Отправка отчета по нарушителям УРВ за вчерашний день'
    code = URV_VIOLATORS_REPORT
    write_history = False

    def get_file(self):
        from src.util.urv.urv_violators import urv_violators_report_xlsx

        return urv_violators_report_xlsx(self.network_id, in_memory=True)


class UrvStatV2Event(BaseRegisteredEvent):
    name = 'Отправка отчета по УРВ за вчерашний день версия 2'
    code = URV_STAT_V2
    write_history = False

    def get_file(self):
        from src.util.urv.create_urv_stat import urv_stat_v2
        dt = date.today() - timedelta(days=1)
        title = f'URV_users_{dt}.xlsx'

        return urv_stat_v2(dt, dt, title=title, network_id=self.network_id, in_memory=True)
