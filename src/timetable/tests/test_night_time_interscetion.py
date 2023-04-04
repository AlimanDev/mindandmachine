import datetime
from src.timetable.worker_day.utils.utils import time_intersection
from src.util.mixins.tests import TestsHelperMixin


class TestNightHoursIntersection(TestsHelperMixin):
    def setUp(self) -> None:
        self.night_hours = (datetime.time(22, 0), datetime.time(6, 0))
        self.must_intersect = [
            (datetime.datetime(2023, 3, 3, 22, 0), datetime.datetime(2023, 3, 4, 4, 0)),
            (datetime.datetime(2023, 3, 3, 21, 0), datetime.datetime(2023, 3, 4, 5, 0)),
            (datetime.datetime(2023, 3, 3, 23, 0), datetime.datetime(2023, 3, 4, 6, 0)),
            (datetime.datetime(2023, 4, 3, 16, 0), datetime.datetime(2023, 4, 4, 11, 0)),
            (datetime.datetime(2023, 3, 3, 22, 0), datetime.datetime(2023, 3, 4, 6, 0)),
            (datetime.datetime(2023, 3, 5, 0, 0), datetime.datetime(2023, 3, 5, 6, 0)),
            (datetime.datetime(2023, 3, 5, 1, 0), datetime.datetime(2023, 3, 5, 3, 0)),
            (datetime.datetime(2023, 3, 3, 22, 0), datetime.datetime(2023, 3, 3, 23, 0)),
            (datetime.datetime(2023, 3, 3, 1, 0), datetime.datetime(2023, 3, 3, 9, 0)),
            (datetime.datetime(2023, 3, 3, 23, 0), datetime.datetime(2023, 3, 4, 11, 0))
        ]
        self.no_intersection = [
            (datetime.datetime(2023, 3, 3, 20, 0), datetime.datetime(2023, 3, 3, 22, 0)),
            (datetime.datetime(2023, 3, 3, 17, 0), datetime.datetime(2023, 3, 3, 21, 0)),
            (datetime.datetime(2023, 3, 3, 6, 0), datetime.datetime(2023, 3, 3, 21, 0)),
            (datetime.datetime(2023, 3, 3, 9, 0), datetime.datetime(2023, 3, 3, 22, 0)),
        ]
        self.double_intersection = (datetime.datetime(2023, 3, 5, 1, 0), datetime.datetime(2023, 3, 5, 23, 0))

    def test_time_intersects(self):
        expected_intersections = [
            (datetime.time(22, 0), datetime.time(4, 0)),
            (datetime.time(22, 0), datetime.time(5, 0)),
            (datetime.time(23, 0), datetime.time(6, 0)),
            (datetime.time(22, 0), datetime.time(6, 0)),
            (datetime.time(22, 0), datetime.time(6, 0)),
            (datetime.time(0, 0), datetime.time(6, 0)),
            (datetime.time(1, 0), datetime.time(3, 0)),
            (datetime.time(22, 0), datetime.time(23, 0)),
            (datetime.time(1, 0), datetime.time(6, 0)),
            (datetime.time(23, 0), datetime.time(6, 0))
        ]
        for date_test in self.must_intersect:
            assert(time_intersection(date_test, self.night_hours) == expected_intersections.pop(0))

    def test_time_no_intersection(self):
        for date_test in self.no_intersection:
            assert(time_intersection(date_test, self.night_hours) is None)

    def test_time_double_intersection(self):
        expected_intersections = (
            (datetime.time(1, 0), datetime.time(6, 0)),
            (datetime.time(22, 0), datetime.time(23, 0))
        )
        assert(time_intersection(self.double_intersection, self.night_hours)) == expected_intersections

    def test_change_night_time(self):
        self.night_hours = (datetime.time(23, 0), datetime.time(6, 0))
        check = (datetime.datetime(2023, 3, 3, 22, 0), datetime.datetime(2023, 3, 4, 6, 0))
        assert(time_intersection(check, self.night_hours) == (datetime.time(23, 0), datetime.time(6, 0)))
