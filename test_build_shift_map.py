from datetime import date
from after5 import CommitTimeInfo, _build_shift_map

FLOOR = 17 * 3600  # 61200
WEEKDAY = date(2024, 1, 15)  # Monday
WEEKEND = date(2024, 1, 13)  # Saturday


def make(h, sod, day=WEEKDAY, utc=None):
    return CommitTimeInfo(h, day, sod, utc if utc is not None else sod)


def test_all_after_floor():
    sm = _build_shift_map([make("a", 18 * 3600), make("b", 19 * 3600)], skip_weekends=True, floor=FLOOR)
    assert sm == {}


def test_all_before_floor_uniform_shift():
    sm = _build_shift_map([make("a", 9 * 3600), make("b", 10 * 3600)], skip_weekends=True, floor=FLOOR)
    assert sm["a"] == FLOOR
    assert sm["b"] == FLOOR + 3600  # relative spacing preserved


def test_single_before_floor():
    sm = _build_shift_map([make("a", 14 * 3600)], skip_weekends=True, floor=FLOOR)
    assert sm["a"] == FLOOR


def test_proportional():
    # first < floor <= last: first → floor, last unchanged
    sm = _build_shift_map([make("a", 15 * 3600), make("b", 20 * 3600)], skip_weekends=True, floor=FLOOR)
    assert sm["a"] == FLOOR
    assert sm["b"] == 20 * 3600


def test_weekend_skip():
    sm = _build_shift_map([make("a", 9 * 3600, day=WEEKEND)], skip_weekends=True, floor=FLOOR)
    assert sm == {}


def test_weekend_include():
    sm = _build_shift_map([make("a", 9 * 3600, day=WEEKEND)], skip_weekends=False, floor=FLOOR)
    assert sm["a"] == FLOOR


def test_mixed_timezones_same_local_day():
    # Two commits on same local day but different UTC offsets (different utc_seconds).
    # _build_shift_map groups by day_local, so both land in the same bucket and
    # receive the same SOD shift — but their new UTC timestamps differ by their offset gap.
    c1 = make("a", 9 * 3600, utc=9 * 3600)           # UTC+0
    c2 = make("b", 10 * 3600, utc=10 * 3600 + 5 * 3600)  # UTC-5 (local 10AM = UTC 3PM)
    sm = _build_shift_map([c1, c2], skip_weekends=True, floor=FLOOR)
    shift = FLOOR - 9 * 3600  # uniform shift applied to both SODs
    assert sm["a"] == c1.utc_seconds + shift
    assert sm["b"] == c2.utc_seconds + shift
