from django.test import TestCase

from src.timetable.break_time_subtractor import (
    HalfNightHalfDayBreakTimeSubtractor,
    InPriorityFromBiggerPartBreakTimeSubtractor,
    InPriorityFromNightBreakTimeSubtractor,
)


class TestBreakTimeSubtractorMixin:
    break_time_subtractor_cls = None

    def _test_break_time_subtract(self,
                                  break_time_seconds, total_seconds, night_seconds, expected_day_hours,
                                  expected_night_hours):
        break_time_subtractor = self.break_time_subtractor_cls(
            break_time_seconds,
            total_seconds,
            night_seconds,
        )
        work_hours_day, work_hours_night = break_time_subtractor.calc()
        self.assertEqual(work_hours_day, round(expected_day_hours, 2))
        self.assertEqual(work_hours_night, round(expected_night_hours, 2))


class TestHalfNightHalfDayBreakTimeSubtractor(TestBreakTimeSubtractorMixin, TestCase):
    break_time_subtractor_cls = HalfNightHalfDayBreakTimeSubtractor

    def test_subtract(self):
        self._test_break_time_subtract(60*60, 60*60*12, 60*60*4, 7.5, 3.5)
        self._test_break_time_subtract(60*60, 60*60*12, 0, 11, 0)


class TestInPriorityFromBiggerPartBreakTimeSubtractor(TestBreakTimeSubtractorMixin, TestCase):
    break_time_subtractor_cls = InPriorityFromBiggerPartBreakTimeSubtractor

    def test_subtract(self):
        self._test_break_time_subtract(60*60, 60*60*12, 60*60*4, 7, 4)
        self._test_break_time_subtract(60*60, 60*60*12, 60*60*8, 4, 7)
        self._test_break_time_subtract(60*60, 70*60, 40*60, 10/60, 0)
        self._test_break_time_subtract(60*60, 70*60, 30*60, 0, 10/60)
        self._test_break_time_subtract(60*60, 30*60, 0, 0, 0)
        self._test_break_time_subtract(60*60, 30*60, 30*60, 0, 0)


class TestInPriorityFromNightBreakTimeSubtractor(TestBreakTimeSubtractorMixin, TestCase):
    break_time_subtractor_cls = InPriorityFromNightBreakTimeSubtractor

    def test_subtract(self):
        self._test_break_time_subtract(60*60, 60*60*12, 60*60*4, 8, 3)
        self._test_break_time_subtract(60*60, 60*60*12, 60*60*8, 4, 7)
        self._test_break_time_subtract(60*60, 70*60, 10*60, 10/60, 0)
        self._test_break_time_subtract(60*60, 50*60, 0, 0, 0)
