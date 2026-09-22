#!/usr/bin/env python3
"""Rewrite git history so all commits land after 5 PM in their local timezone."""
import argparse
import random
import sys

try:
    import git_filter_repo as fr
except ImportError:
    sys.exit("git-filter-repo not found: pip install git-filter-repo")

FIVE_PM = 17 * 3600
THREE_HOURS = 3 * 3600


def _shift_date(date_bytes: bytes) -> bytes:
    ts_str, offset_str = date_bytes.decode().split()
    timestamp = int(ts_str)

    sign = 1 if offset_str[0] == "+" else -1
    utc_offset = sign * (int(offset_str[1:3]) * 3600 + int(offset_str[3:5]) * 60)

    local_sod = (timestamp + utc_offset) % 86400  # seconds into local day

    if local_sod < FIVE_PM:
        target = FIVE_PM + random.randint(0, THREE_HOURS - 1)
        timestamp += target - local_sod

    return f"{timestamp} {offset_str}".encode()


def make_callback(name: str | None, email: str | None):
    def commit_callback(commit, metadata):
        commit.author_date = _shift_date(commit.author_date)
        commit.committer_date = _shift_date(commit.committer_date)
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
    p.add_argument("--seed", type=int, help="random seed for reproducible output")
    args = p.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    fr_args = fr.FilteringOptions.parse_args(["--force", "--repo", args.repo])
    fr.RepoFilter(fr_args, commit_callback=make_callback(args.name, args.email)).run()


if __name__ == "__main__":
    main()
