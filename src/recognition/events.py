from src.events.registry import BaseRegisteredEvent

from datetime import date, timedelta


URV_STAT = 'urv_stat'
URV_STAT_TODAY = 'urv_stat_today'


class UrvStatEvent(BaseRegisteredEvent):
    name = 'Отправка отчета по УРВ за вчерашний день'
    code = URV_STAT
    write_history = False

    def get_file(self):
        from src.util.urv.create_urv_stat import main as create_urv
        dt = date.today() - timedelta(days=1)
        title = f'URV_{dt}.xlsx'

        return create_urv(dt, dt, title=title, network_id=self.network_id, in_memory=True)
        

class UrvStatTodayEvent(BaseRegisteredEvent):
    name = 'Отправка отчета по УРВ за сегодняшний день'
    code = URV_STAT_TODAY
    write_history = False

    def get_file(self):
        from src.util.urv.create_urv_stat import main as create_urv
        dt = date.today()
        title = f'URV_today_{dt}.xlsx'

        return create_urv(dt, dt, title=title, network_id=self.network_id, in_memory=True)
