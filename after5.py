#!/usr/bin/env python3
"""Rewrite git history so all commits land after 5 PM in their local timezone."""
import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from typing import NamedTuple

try:
    import git_filter_repo as fr
except ImportError:
    sys.exit("git-filter-repo not found: something is terribly wrong")

FLOOR = 17 * 3600  # 5 PM in seconds # todo, use paslirsed / default

CommitHash = str
UtcTimestamp = int
ShiftMap = dict[CommitHash, UtcTimestamp]

class CommitTimeInfo(NamedTuple):
    commit_hash: CommitHash
    day_local: date
    seconds_after_midnight_local: int
    utc_seconds: UtcTimestamp

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
        local_ts = ts + _parse_utc_offset(offset_str)
        commits.append(CommitTimeInfo(
            commit_hash=commit_hash,
            day_local=date(1970, 1, 1) + timedelta(days=local_ts // 86400),
            seconds_after_midnight_local=local_ts % 86400,
            utc_seconds=ts,
        ))
    return commits


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _build_shift_map(commits: list[CommitTimeInfo], skip_weekends: bool) -> ShiftMap:
    """Returns {commit_hash: new_utc_timestamp}."""
    by_day: dict[date, list[CommitTimeInfo]] = defaultdict(list)
    for commit in commits:
        by_day[commit.day_local].append(commit)

    shift_map: ShiftMap = {}

    for local_day, day_commits in by_day.items():
        if skip_weekends and _is_weekend(local_day):
            continue

        day_commits.sort(key=lambda c: c.seconds_after_midnight_local)
        first_sod = day_commits[0].seconds_after_midnight_local
        last_sod = day_commits[-1].seconds_after_midnight_local

        if first_sod >= FLOOR:
            continue

        for commit in day_commits:
            sod = commit.seconds_after_midnight_local
            if last_sod < FLOOR:
                new_sod = FLOOR + (sod - first_sod)
            else:
                ratio = (sod - first_sod) / (last_sod - first_sod)
                new_sod = FLOOR + ratio * (last_sod - FLOOR)

            shift_map[commit.commit_hash] = commit.utc_seconds + (int(new_sod) - sod)

    return shift_map


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
    p.add_argument("--floor-time", help="set time that all comitts should appear after (default 5pm")
    p.add_argument("--include-weekends", action="store_true",
                   help="also rewrite weekend commits (default: skip weekends)")
    args = p.parse_args()

    commits = _collect_commits(args.repo)
    shift_map = _build_shift_map(commits, skip_weekends=not args.include_weekends)

    fr_args = fr.FilteringOptions.parse_args(["--force", "--repo", args.repo])
    fr.RepoFilter(fr_args, commit_callback=make_callback(shift_map, args.name, args.email)).run()


if __name__ == "__main__":
    main()
