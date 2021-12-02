class BaseBreakTimeSubtractor:
    """
    Базовый класс для алгоритма определения откуда вычитать время перерывов (из дневных или ночных часов)
    """

    def __init__(self, break_time_seconds, total_seconds, night_seconds, round_to=2):
        self.break_time_seconds = break_time_seconds
        self.total_seconds = total_seconds
        self.night_seconds = night_seconds
        self.day_seconds = total_seconds - night_seconds
        self.round_to = round_to

    def _clean_work_hours(self, work_hours_day, work_hours_night):
        return max(work_hours_day, 0), max(work_hours_night, 0)

    def calc(self):
        raise NotImplementedError


class HalfNightHalfDayBreakTimeSubtractor(BaseBreakTimeSubtractor):
    def calc(self):
        break_time_half_seconds = self.break_time_seconds / 2
        if self.night_seconds > break_time_half_seconds:
            work_hours_day = round((self.day_seconds - break_time_half_seconds) / 3600, self.round_to)
            work_hours_night = round((self.night_seconds - break_time_half_seconds) / 3600, self.round_to)
        else:
            subtract_from_day_seconds = self.break_time_seconds - self.night_seconds
            work_hours_night = 0.0
            work_hours_day = round((self.day_seconds - subtract_from_day_seconds) / 3600,
                                   self.round_to)
        return self._clean_work_hours(work_hours_day, work_hours_night)


class InPriorityFromNightBreakTimeSubtractor(BaseBreakTimeSubtractor):
    def calc(self):
        if self.night_seconds >= self.break_time_seconds:
            work_hours_day = round(self.day_seconds / 3600, self.round_to)
            work_hours_night = round((self.night_seconds - self.break_time_seconds) / 3600, self.round_to)
        else:
            subtract_from_day_seconds = self.break_time_seconds - self.night_seconds
            work_hours_night = 0.0
            work_hours_day = round((self.day_seconds - subtract_from_day_seconds) / 3600, self.round_to)
        return self._clean_work_hours(work_hours_day, work_hours_night)


class InPriorityFromBiggerPartBreakTimeSubtractor(BaseBreakTimeSubtractor):
    def calc(self):
        if self.day_seconds > self.night_seconds:
            if self.day_seconds >= self.break_time_seconds:
                work_hours_day = round((self.day_seconds - self.break_time_seconds) / 3600, self.round_to)
                work_hours_night = round(self.night_seconds / 3600, self.round_to)
            else:
                subtract_from_night_seconds = self.break_time_seconds - self.day_seconds
                work_hours_day = 0.0
                work_hours_night = round((self.night_seconds - subtract_from_night_seconds) / 3600, self.round_to)
        else:
            if self.night_seconds >= self.break_time_seconds:
                work_hours_night = round((self.night_seconds - self.break_time_seconds) / 3600, self.round_to)
                work_hours_day = round(self.day_seconds / 3600, self.round_to)
            else:
                subtract_from_day_seconds = self.break_time_seconds - self.night_seconds
                work_hours_night = 0.0
                work_hours_day = round((self.day_seconds - subtract_from_day_seconds) / 3600, self.round_to)
        return self._clean_work_hours(work_hours_day, work_hours_night)


# TODO: тесты
break_time_subtractor_map = {
    'default': HalfNightHalfDayBreakTimeSubtractor,
    'in_priority_from_night': InPriorityFromNightBreakTimeSubtractor,
    'in_priority_from_bigger_part': InPriorityFromBiggerPartBreakTimeSubtractor,
    # 'proportionally': ProportionallyBreakTimeSubtractor,  # TODO: ?
}
