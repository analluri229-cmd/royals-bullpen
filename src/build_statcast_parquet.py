"""Step 3: turn the Statcast CSV pulls into one slim parquet.

Reads data/raw/statcast_2026.csv.gz (the existing full-column pull) plus any
chunk files from src/pull_statcast.py in data/raw/statcast_chunks/, keeps
the Step 3 columns (plus umpire and age_pit when present), keeps regular-season
games only, drops duplicate pitches, and writes data/raw/statcast_2026.parquet.
Skips the work if the parquet already exists, unless --force is passed.

Usage:  python -m src.build_statcast_parquet [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.config import (DATA_RAW, KEEP_COLUMNS, OPTIONAL_COLUMNS,
                        STATCAST_CSV_GZ, STATCAST_PARQUET)

CHUNK_ROWS = 200_000
PITCH_KEY = ["game_pk", "at_bat_number", "pitch_number"]
STRING_COLS = ("events", "description", "pitch_type", "bb_type", "type",
               "inning_topbot", "p_throws", "stand", "home_team", "away_team",
               "player_name", "game_type")


def select_columns(header: list[str]) -> list[str]:
    missing = [c for c in KEEP_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"Statcast file is missing required columns: {missing}")
    return KEEP_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in header]


def source_files(main: Path = STATCAST_CSV_GZ) -> list[Path]:
    files = [main] if main.exists() else []
    files += sorted((DATA_RAW / "statcast_chunks").glob("statcast_*.csv*"))
    if not files:
        raise FileNotFoundError("No Statcast CSVs found in data/raw.")
    return files


def read_one(path: Path) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0).columns.tolist()
    cols = select_columns(header)
    parts = [c[c["game_type"] == "R"]
             for c in pd.read_csv(path, usecols=cols, chunksize=CHUNK_ROWS, low_memory=False)]
    return pd.concat(parts, ignore_index=True)[cols]


def combine(frames: list[pd.DataFrame]) -> pd.DataFrame:
    cols = list(dict.fromkeys(c for f in frames for c in f.columns))
    df = pd.concat([f.reindex(columns=cols) for f in frames], ignore_index=True)
    df = df.drop_duplicates(subset=PITCH_KEY, keep="first")
    df["game_date"] = pd.to_datetime(df["game_date"])
    for c in STRING_COLS:
        df[c] = df[c].astype("string")
    return df.sort_values(["game_date", "game_pk", *PITCH_KEY[1:]], ignore_index=True)


def build(dst: Path = STATCAST_PARQUET, force: bool = False) -> pd.DataFrame:
    if dst.exists() and not force:
        print(f"{dst} already exists; loading it (use --force to rebuild).")
        return pd.read_parquet(dst)
    files = source_files()
    print("reading:", ", ".join(p.name for p in files))
    df = combine([read_one(p) for p in files])
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dst, index=False)
    return df


def report(df: pd.DataFrame) -> None:
    per_day = df.groupby(df["game_date"].dt.date)["game_pk"].nunique()
    print(f"rows: {len(df):,}  games: {df.game_pk.nunique():,}  pitchers: {df.pitcher.nunique():,}")
    print(f"dates: {per_day.index.min()} to {per_day.index.max()} ({len(per_day)} game days)")
    if per_day.index.min() > pd.Timestamp("2026-03-27").date():
        print("WARNING: data starts after opening week. Run src.pull_statcast for the missing window.")
    for c in OPTIONAL_COLUMNS:
        fill = f"{df[c].notna().mean():.1%} of pitches filled" if c in df else "not in source"
        print(f"{c}: {fill}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    report(build(force=args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
