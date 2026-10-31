"""Step 3: pull Statcast pitches in 7-day chunks with pybaseball (cached).

The existing full pull (data/raw/statcast_2026.csv.gz) starts on 2026-04-25,
so the first month of the season is missing. This script fills any date
window into data/raw/statcast_chunks/, one CSV per 7-day chunk, and skips a
chunk whose file already exists. build_statcast_parquet.py merges these
chunks with the main file.

Baseball Savant can't be reached from the Claude cloud workspace, so run this
on Windows in VS Code:

    python -m src.pull_statcast --start 2026-03-25 --end 2026-04-24
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from src.config import DATA_RAW

CHUNK_DIR = DATA_RAW / "statcast_chunks"
SEASON_START = date(2026, 3, 25)
SEASON_END = date(2026, 9, 27)


def chunks(start: date, end: date, days: int = 7):
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=days - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def pull(start: date, end: date, force: bool = False) -> None:
    from pybaseball import cache, statcast  # imported here so tests don't need it
    cache.enable()
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    for a, b in chunks(start, end):
        path = CHUNK_DIR / f"statcast_{a:%Y%m%d}_{b:%Y%m%d}.csv.gz"
        if path.exists() and not force:
            print(f"skip {path.name} (cached)")
            continue
        df = statcast(start_dt=f"{a:%Y-%m-%d}", end_dt=f"{b:%Y-%m-%d}")
        if df is None or df.empty:
            print(f"{a} to {b}: no rows")
            continue
        df = df[df["game_type"] == "R"]
        df.to_csv(path, index=False)
        print(f"{a} to {b}: {len(df):,} pitches, {df.game_pk.nunique()} games -> {path.name}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=f"{SEASON_START}")
    ap.add_argument("--end", default=f"{SEASON_END}")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    pull(date.fromisoformat(a.start), date.fromisoformat(a.end), a.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
