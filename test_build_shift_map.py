from datetime import date, datetime, timedelta, timezone
from after5 import CommitTimeInfo, _build_shift_map

FLOOR = 17 * 3600  # 61200
WEEKDAY = date(2024, 1, 15)  # Monday
WEEKEND = date(2024, 1, 13)  # Saturday
_EPOCH = date(1970, 1, 1)


def _day_offset(day: date) -> int:
    return (day - _EPOCH).days * 86400


def make(h, secs, day=WEEKDAY, tz_offset=0):
    tz = timezone(timedelta(seconds=tz_offset))
    dt = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(seconds=secs)
    return CommitTimeInfo(h, dt)


def test_all_after_floor():
    sm = _build_shift_map([make("a", 18 * 3600), make("b", 19 * 3600)], skip_weekends=True, floor=FLOOR)
    assert sm == {}


def test_all_before_floor_uniform_shift():
    sm = _build_shift_map([make("a", 9 * 3600), make("b", 10 * 3600)], skip_weekends=True, floor=FLOOR)
    base = _day_offset(WEEKDAY)
    assert sm["a"] == base + FLOOR
    assert sm["b"] == base + FLOOR + 3600  # relative spacing preserved


def test_single_before_floor():
    sm = _build_shift_map([make("a", 14 * 3600)], skip_weekends=True, floor=FLOOR)
    assert sm["a"] == _day_offset(WEEKDAY) + FLOOR


def test_after_floor_untouched():
    # commit already past floor is not forbidden, stays out of shift_map
    sm = _build_shift_map([make("a", 15 * 3600), make("b", 20 * 3600)], skip_weekends=True, floor=FLOOR)
    assert sm["a"] == _day_offset(WEEKDAY) + FLOOR
    assert "b" not in sm


def test_ceiling_skips_early_morning():
    # commit before ceiling is outside the forbidden zone — not shifted
    CEILING = 9 * 3600
    sm = _build_shift_map([make("a", 7 * 3600)], skip_weekends=True, floor=FLOOR, ceiling=CEILING)
    assert sm == {}


def test_ceiling_shifts_workday_commit():
    CEILING = 9 * 3600
    sm = _build_shift_map([make("a", 10 * 3600)], skip_weekends=True, floor=FLOOR, ceiling=CEILING)
    assert sm["a"] == _day_offset(WEEKDAY) + FLOOR


def test_ceiling_mixed_day():
    # early-morning commit (before ceiling) + workday commit (in zone): only workday shifts
    CEILING = 9 * 3600
    sm = _build_shift_map(
        [make("early", 7 * 3600), make("work", 11 * 3600)],
        skip_weekends=True, floor=FLOOR, ceiling=CEILING,
    )
    assert "early" not in sm
    assert sm["work"] == _day_offset(WEEKDAY) + FLOOR


def test_weekend_skip():
    sm = _build_shift_map([make("a", 9 * 3600, day=WEEKEND)], skip_weekends=True, floor=FLOOR)
    assert sm == {}


def test_weekend_include():
    sm = _build_shift_map([make("a", 9 * 3600, day=WEEKEND)], skip_weekends=False, floor=FLOOR)
    assert sm["a"] == _day_offset(WEEKEND) + FLOOR


def test_mixed_timezones_same_local_day():
    # Two commits on same local day but different UTC offsets.
    # _build_shift_map groups by dt.date(), so both land in the same bucket and
    # receive the same SOD shift — but their new UTC timestamps differ by their offset gap.
    c1 = make("a", 9 * 3600)                        # UTC+0, local 9AM
    c2 = make("b", 10 * 3600, tz_offset=-5 * 3600)  # UTC-5, local 10AM = UTC 3PM
    sm = _build_shift_map([c1, c2], skip_weekends=True, floor=FLOOR)
    shift = FLOOR - 9 * 3600
    assert sm["a"] == int(c1.dt.timestamp()) + shift
    assert sm["b"] == int(c2.dt.timestamp()) + shift
