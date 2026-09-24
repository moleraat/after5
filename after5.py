#!/usr/bin/env python3
"""Rewrite git history so all commits land after 5 PM in their local timezone."""
import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

try:
    import git_filter_repo as fr
except ImportError:
    sys.exit("git-filter-repo not found: something is terribly wrong")


CommitHash = str
UtcTimestamp = int
ShiftMap = dict[CommitHash, UtcTimestamp]

class CommitTimeInfo(NamedTuple):
    commit_hash: CommitHash
    dt: datetime  # timezone-aware, commit's local tz


def _day_secs(dt: datetime) -> int:
    return dt.hour * 3600 + dt.minute * 60 + dt.second

def _parse_floor_time(s: str) -> int:
    try:
        h, m = s.split(":")
        return int(h) * 3600 + int(m) * 60
    except (ValueError, AttributeError):
        raise SystemExit(f"Invalid floor-time '{s}': expected HH:MM")


def _parse_utc_offset(offset_str: str) -> int:
    sign = 1 if offset_str[0] == "+" else -1
    return sign * (int(offset_str[1:3]) * 3600 + int(offset_str[3:5]) * 60)


def _collect_commits(repo_path: str) -> list[CommitTimeInfo]:
    result = subprocess.run(
        ["git", "-C", repo_path, "log", "--format=%H %ad", "--date=raw"],
        capture_output=True, text=True, check=True,
    )
    commits = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        commit_hash, ts_str, offset_str = line.split()
        ts = int(ts_str)
        tz = timezone(timedelta(seconds=_parse_utc_offset(offset_str)))
        commits.append(CommitTimeInfo(
            commit_hash=commit_hash,
            dt=datetime.fromtimestamp(ts, tz=tz),
        ))
    return commits


def _build_shift_map(commits: list[CommitTimeInfo], skip_weekends: bool, floor: int) -> ShiftMap:
    """Returns {commit_hash: new_utc_timestamp}."""
    by_day: dict[date, list[CommitTimeInfo]] = defaultdict(list)
    for commit in commits:
        by_day[commit.dt.date()].append(commit)

    shift_map: ShiftMap = {}

    for local_day, day_commits in by_day.items():
        if skip_weekends and local_day.weekday() >= 5:
            continue

        day_commits.sort(key=lambda c: c.dt.time())
        first_secs = _day_secs(day_commits[0].dt)
        last_secs = _day_secs(day_commits[-1].dt)

        if first_secs >= floor:
            continue

        for commit in day_commits:
            secs = _day_secs(commit.dt)
            if last_secs < floor:
                new_secs = floor + (secs - first_secs)
            else:
                ratio = (secs - first_secs) / (last_secs - first_secs)
                new_secs = floor + ratio * (last_secs - floor)

            shift_map[commit.commit_hash] = int(commit.dt.timestamp()) + (int(new_secs) - secs)

    return shift_map


def _print_dry_run(commits: list[CommitTimeInfo], shift_map: ShiftMap) -> None:
    if not shift_map:
        print("No commits to shift.")
        return
    old_utc = {c.commit_hash: int(c.dt.timestamp()) for c in commits}
    for h, new_ts in shift_map.items():
        old = datetime.fromtimestamp(old_utc[h], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        new = datetime.fromtimestamp(new_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"{h[:8]}  {old}  →  {new}")


def _redate(date_bytes: bytes, new_ts: int) -> bytes:
    _, offset_str = date_bytes.decode().split()
    return f"{new_ts} {offset_str}".encode()


def make_callback(shift_map: ShiftMap, name: str | None, email: str | None):
    def commit_callback(commit, metadata):
        commit_hash = commit.original_id.decode()
        if commit_hash in shift_map:
            new_ts = shift_map[commit_hash]
            commit.author_date = _redate(commit.author_date, new_ts)
            commit.committer_date = _redate(commit.committer_date, new_ts)
        if name:
            commit.author_name = commit.committer_name = name.encode()
        if email:
            commit.author_email = commit.committer_email = email.encode()

    return commit_callback


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo", help="path to the git repo to rewrite")
    p.add_argument("--name", help="replace author/committer name")
    p.add_argument("--email", help="replace author/committer email")
    p.add_argument("--floor-time", default="17:00", help="earliest allowed commit time (HH:MM, default 17:00)")
    p.add_argument("--dry-run", action="store_true",
                   help="print commits that would be shifted without rewriting history")
    p.add_argument("--include-weekends", action="store_true",
                   help="also rewrite weekend commits (default: skip weekends)")
    args = p.parse_args()

    floor = _parse_floor_time(args.floor_time)
    commits = _collect_commits(args.repo)
    shift_map = _build_shift_map(commits, skip_weekends=not args.include_weekends, floor=floor)

    if args.dry_run:
        _print_dry_run(commits, shift_map)
        return

    fr_args = fr.FilteringOptions.parse_args(["--force", "--repo", args.repo])
    fr.RepoFilter(fr_args, commit_callback=make_callback(shift_map, args.name, args.email)).run()


if __name__ == "__main__":
    main()
