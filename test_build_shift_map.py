from datetime import date, datetime, timedelta, timezone
from after5 import build_shift_map

WORK_END = 17 * 3600  # 61200
WEEKDAY  = date(2024, 1, 15)  # Monday
TUESDAY  = date(2024, 1, 16)  # Tuesday
WEEKEND  = date(2024, 1, 13)  # Saturday
_EPOCH   = date(1970, 1, 1)


def _day_offset(day: date) -> int:
    return (day - _EPOCH).days * 86400


def make(secs, day=WEEKDAY, tz_offset=0) -> datetime:
    tz = timezone(timedelta(seconds=tz_offset))
    return datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(seconds=secs)


def test_hourly_redistribution():
    # 24 commits one per hour on a weekday.
    # Commits before work_start (00:00-08:00) are untouched.
    # All commits from work_start onward are redistributed proportionally
    # into [work_end, day_end) — day_end is exclusive so no commit lands exactly at midnight.
    WORK_START = 9 * 3600
    WORK_END   = 17 * 3600
    DAY_END    = 24 * 3600
    commits = {str(h): make(h * 3600) for h in range(24)}
    sm = build_shift_map(
        commits,
        work_start=WORK_START,
        work_end=WORK_END,
        day_end=DAY_END,
        skip_weekends=True,
    )
    base = _day_offset(WEEKDAY)

    for h in range(9):
        assert str(h) not in sm, f"commit at {h}:00 should be untouched"

    # source span anchored at day_end (exclusive), not last commit:
    #   [work_start, day_end) = 15h; target [work_end, day_end) = 7h; scale = 7/15
    source_span = DAY_END - WORK_START
    target_span = DAY_END - WORK_END
    for h in range(9, 24):
        expected = base + WORK_END + int((h * 3600 - WORK_START) * target_span / source_span)
        assert sm[str(h)] == expected, f"commit at {h}:00: expected {expected}, got {sm.get(str(h))}"


def test_order_preserved():
    # Irregular commit times across and after the work window.
    # After redistribution, their relative order must be identical to the original.
    WORK_START = 9 * 3600
    WORK_END   = 17 * 3600
    DAY_END    = 24 * 3600
    times = [
        10 * 3600,               # 10:00
        11 * 3600 + 1800,        # 11:30
        14 * 3600 + 900,         # 14:15
        16 * 3600 + 3540,        # 16:59
        19 * 3600,               # 19:00  (already after work_end, still redistributed)
        22 * 3600 + 2700,        # 22:45
    ]
    commits = {str(i): make(t) for i, t in enumerate(times)}
    sm = build_shift_map(commits, work_start=WORK_START, work_end=WORK_END, day_end=DAY_END, skip_weekends=True)

    shifted = [sm[str(i)] for i in range(len(times))]
    assert shifted == sorted(shifted), "order not preserved after redistribution"
    assert len(set(shifted)) == len(shifted), "redistributed timestamps must be unique"


def test_work_start_midnight():
    # work_start=0 means every commit on the day is redistributed — none untouched.
    WORK_START = 0
    WORK_END   = 17 * 3600
    DAY_END    = 24 * 3600
    commits = {str(h): make(h * 3600) for h in range(24)}
    sm = build_shift_map(commits, work_start=WORK_START, work_end=WORK_END, day_end=DAY_END, skip_weekends=True)

    assert set(sm.keys()) == {str(h) for h in range(24)}, "all 24 commits should be redistributed"

    base = _day_offset(WEEKDAY)
    for key, ts in sm.items():
        sod = ts - base
        assert WORK_END <= sod < DAY_END, f"commit {key} landed outside [work_end, day_end): sod={sod}"


def test_narrow_evening_window():
    # work_end=22:00, day_end=23:00 — only 1h target window.
    # All redistributed commits must land in that 1-hour slot, in order.
    WORK_START = 9 * 3600
    WORK_END   = 22 * 3600
    DAY_END    = 23 * 3600
    commits = {str(h): make(h * 3600) for h in range(9, 23)}
    sm = build_shift_map(commits, work_start=WORK_START, work_end=WORK_END, day_end=DAY_END, skip_weekends=True)

    base = _day_offset(WEEKDAY)
    for key, ts in sm.items():
        sod = ts - base
        assert WORK_END <= sod < DAY_END, f"commit {key} outside [22:00, 23:00): sod={sod}"

    shifted = [sm[str(h)] for h in range(9, 23)]
    assert shifted == sorted(shifted), "order not preserved in narrow window"


def test_two_weekdays_no_spillover():
    # Two full weekdays (Mon + Tue), 24 commits each.
    # Invariants:
    #   1. early-morning commits (before work_start) are untouched on both days
    #   2. no redistributed commit spills from Monday into Tuesday
    #   3. no redistributed commit lands during work hours
    #   4. within each day, redistributed commits are in increasing order
    WORK_START = 9 * 3600
    WORK_END   = 17 * 3600
    DAY_END    = 24 * 3600

    mon = {f"mon{h}": make(h * 3600, day=WEEKDAY)  for h in range(24)}
    tue = {f"tue{h}": make(h * 3600, day=TUESDAY) for h in range(24)}
    sm = build_shift_map(
        {**mon, **tue},
        work_start=WORK_START, work_end=WORK_END, day_end=DAY_END, skip_weekends=True,
    )

    base_mon = _day_offset(WEEKDAY)
    base_tue = _day_offset(TUESDAY)

    # 1. untouched commits not in shift map
    for h in range(9):
        assert f"mon{h}" not in sm
        assert f"tue{h}" not in sm

    # 2. no Monday commit spills into Tuesday
    for h in range(9, 24):
        assert sm[f"mon{h}"] < base_tue, f"mon{h} spilled into Tuesday"

    # 3. no work-hours timestamps
    for h in range(9, 24):
        mon_sod = sm[f"mon{h}"] - base_mon
        tue_sod = sm[f"tue{h}"] - base_tue
        assert not (WORK_START <= mon_sod < WORK_END), f"mon{h} landed in work hours"
        assert not (WORK_START <= tue_sod < WORK_END), f"tue{h} landed in work hours"

    # 4. order preserved within each day
    mon_shifted = [sm[f"mon{h}"] for h in range(9, 24)]
    tue_shifted = [sm[f"tue{h}"] for h in range(9, 24)]
    assert mon_shifted == sorted(mon_shifted), "Monday order not preserved"
    assert tue_shifted == sorted(tue_shifted), "Tuesday order not preserved"


# def test_all_after_work_end():
#     sm = build_shift_map({"a": make(18 * 3600), "b": make(19 * 3600)}, skip_weekends=True, work_end=WORK_END)
#     assert sm == {}
#
#
# def test_all_before_work_end_uniform_shift():
#     sm = build_shift_map({"a": make(9 * 3600), "b": make(10 * 3600)}, skip_weekends=True, work_end=WORK_END)
#     base = _day_offset(WEEKDAY)
#     assert sm["a"] == base + WORK_END
#     assert sm["b"] == base + WORK_END + 3600  # relative spacing preserved
#
#
# def test_single_before_work_end():
#     sm = build_shift_map({"a": make(14 * 3600)}, skip_weekends=True, work_end=WORK_END)
#     assert sm["a"] == _day_offset(WEEKDAY) + WORK_END
#
#
# def test_after_work_end_untouched():
#     # commit already past work_end is not forbidden, stays out of shift_map
#     sm = build_shift_map({"a": make(15 * 3600), "b": make(20 * 3600)}, skip_weekends=True, work_end=WORK_END)
#     assert sm["a"] == _day_offset(WEEKDAY) + WORK_END
#     assert "b" not in sm
#
#
# def test_work_start_skips_early_morning():
#     # commit before work_start is outside the forbidden zone — not shifted
#     WORK_START = 9 * 3600
#     sm = build_shift_map({"a": make(7 * 3600)}, skip_weekends=True, work_end=WORK_END, work_start=WORK_START)
#     assert sm == {}
#
#
# def test_work_start_shifts_workday_commit():
#     WORK_START = 9 * 3600
#     sm = build_shift_map({"a": make(10 * 3600)}, skip_weekends=True, work_end=WORK_END, work_start=WORK_START)
#     assert sm["a"] == _day_offset(WEEKDAY) + WORK_END
#
#
# def test_work_start_mixed_day():
#     # early-morning commit (before work_start) + workday commit (in zone): only workday shifts
#     WORK_START = 9 * 3600
#     sm = build_shift_map(
#         {"early": make(7 * 3600), "work": make(11 * 3600)},
#         skip_weekends=True, work_end=WORK_END, work_start=WORK_START,
#     )
#     assert "early" not in sm
#     assert sm["work"] == _day_offset(WEEKDAY) + WORK_END
#
#
# def test_weekend_skip():
#     sm = build_shift_map({"a": make(9 * 3600, day=WEEKEND)}, skip_weekends=True, work_end=WORK_END)
#     assert sm == {}
#
#
# def test_weekend_include():
#     sm = build_shift_map({"a": make(9 * 3600, day=WEEKEND)}, skip_weekends=False, work_end=WORK_END)
#     assert sm["a"] == _day_offset(WEEKEND) + WORK_END
#
#
# def test_mixed_timezones_same_local_day():
#     # Two commits on same local day but different UTC offsets.
#     # _build_shift_map groups by dt.date(), so both land in the same bucket and
#     # receive the same shift — but their new UTC timestamps differ by their offset gap.
#     c1 = make(9 * 3600)                        # UTC+0, local 9AM
#     c2 = make(10 * 3600, tz_offset=-5 * 3600)  # UTC-5, local 10AM = UTC 3PM
#     sm = build_shift_map({"a": c1, "b": c2}, skip_weekends=True, work_end=WORK_END)
#     shift = WORK_END - 9 * 3600
#     assert sm["a"] == int(c1.timestamp()) + shift
#     assert sm["b"] == int(c2.timestamp()) + shift
