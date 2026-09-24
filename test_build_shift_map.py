from datetime import date, datetime, timedelta, timezone
from after5 import CommitTimeInfo, _build_shift_map

WORK_END = 17 * 3600  # 61200
WEEKDAY = date(2024, 1, 15)  # Monday
WEEKEND = date(2024, 1, 13)  # Saturday
_EPOCH = date(1970, 1, 1)


def _day_offset(day: date) -> int:
    return (day - _EPOCH).days * 86400


def make(h, secs, day=WEEKDAY, tz_offset=0):
    tz = timezone(timedelta(seconds=tz_offset))
    dt = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(seconds=secs)
    return CommitTimeInfo(h, dt)


def test_all_after_work_end():
    sm = _build_shift_map([make("a", 18 * 3600), make("b", 19 * 3600)], skip_weekends=True, work_end=WORK_END)
    assert sm == {}


def test_all_before_work_end_uniform_shift():
    sm = _build_shift_map([make("a", 9 * 3600), make("b", 10 * 3600)], skip_weekends=True, work_end=WORK_END)
    base = _day_offset(WEEKDAY)
    assert sm["a"] == base + WORK_END
    assert sm["b"] == base + WORK_END + 3600  # relative spacing preserved


def test_single_before_work_end():
    sm = _build_shift_map([make("a", 14 * 3600)], skip_weekends=True, work_end=WORK_END)
    assert sm["a"] == _day_offset(WEEKDAY) + WORK_END


def test_after_work_end_untouched():
    # commit already past work_end is not forbidden, stays out of shift_map
    sm = _build_shift_map([make("a", 15 * 3600), make("b", 20 * 3600)], skip_weekends=True, work_end=WORK_END)
    assert sm["a"] == _day_offset(WEEKDAY) + WORK_END
    assert "b" not in sm


def test_work_start_skips_early_morning():
    # commit before work_start is outside the forbidden zone — not shifted
    WORK_START = 9 * 3600
    sm = _build_shift_map([make("a", 7 * 3600)], skip_weekends=True, work_end=WORK_END, work_start=WORK_START)
    assert sm == {}


def test_work_start_shifts_workday_commit():
    WORK_START = 9 * 3600
    sm = _build_shift_map([make("a", 10 * 3600)], skip_weekends=True, work_end=WORK_END, work_start=WORK_START)
    assert sm["a"] == _day_offset(WEEKDAY) + WORK_END


def test_work_start_mixed_day():
    # early-morning commit (before work_start) + workday commit (in zone): only workday shifts
    WORK_START = 9 * 3600
    sm = _build_shift_map(
        [make("early", 7 * 3600), make("work", 11 * 3600)],
        skip_weekends=True, work_end=WORK_END, work_start=WORK_START,
    )
    assert "early" not in sm
    assert sm["work"] == _day_offset(WEEKDAY) + WORK_END


def test_weekend_skip():
    sm = _build_shift_map([make("a", 9 * 3600, day=WEEKEND)], skip_weekends=True, work_end=WORK_END)
    assert sm == {}


def test_weekend_include():
    sm = _build_shift_map([make("a", 9 * 3600, day=WEEKEND)], skip_weekends=False, work_end=WORK_END)
    assert sm["a"] == _day_offset(WEEKEND) + WORK_END


def test_mixed_timezones_same_local_day():
    # Two commits on same local day but different UTC offsets.
    # _build_shift_map groups by dt.date(), so both land in the same bucket and
    # receive the same shift — but their new UTC timestamps differ by their offset gap.
    c1 = make("a", 9 * 3600)                        # UTC+0, local 9AM
    c2 = make("b", 10 * 3600, tz_offset=-5 * 3600)  # UTC-5, local 10AM = UTC 3PM
    sm = _build_shift_map([c1, c2], skip_weekends=True, work_end=WORK_END)
    shift = WORK_END - 9 * 3600
    assert sm["a"] == int(c1.dt.timestamp()) + shift
    assert sm["b"] == int(c2.dt.timestamp()) + shift
