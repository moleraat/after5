# 😼 after5

If you're like me, there's nothing better than stealing company time. Easily rewrite commit history to be after 5pm. 

Optionally install a post-commit hook to rewrite going forward, rewrite the author and email commit info, set different working hours other than 9-5pm, or only rewrite history within a specified date range.

Builds on top of [git-filter-repo](https://github.com/newren/git-filter-repo#simple-example-with-comparisons)


## Install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
curl -o ~/.local/bin/after5 https://raw.githubusercontent.com/moleraat/after5/main/after5
chmod +x ~/.local/bin/after5
```

## Usage

```sh
# Rewrite history (git-filter-repo recommends always running on a fresh clone)
after5

# Preview what would be shifted
after5 --dry-run

# Override default no-no zone
after5 --work-start 10:00 --work-end 18:00 --dry-run

# Snipe rewrite a small window (e.g. you were travelling and had a different schedule)
after5 --after 2026-05-01 --before 2026-06-01

# Option to independently rewrite name and email info (e.g. you have a different git profile)
after5 --name sneaky --email beaky@goodemployee.com
```

### After rewriting

`git-filter-repo` removes the `origin` remote after rewriting as a safety measure. To push:

```sh
git remote add origin <your-repo-url>
git push --force
```

## How it Works

Running `after5` in the target repo goes through the commit history day by day. It collects commits in the interval `[work_start, day_end)` and maps them to the interval `(work_end, day_end)`. Anything before `work_start` is ignored. 

After running the backfill with `after5`, a post-commit hook is installed in the target repo. Going forward, commits are automatically rewritten with the settings you originally ran the backfill with (e.g. work hours, author name, etc).
