"""Pitch mix by count and batter hand (Baseball Savant "Pitch Mix" view), relief pitches only.

Table: outputs/tables/pitch_mix_by_count.csv, one row per pitcher x stand x count x pitch_type
with n and usage_pct (share of that pitcher's pitches in that count vs that hand).
count = "B-S" for the 12 counts, plus "All".

Usage:  python -m src.pitch_mix        (needs data/processed/pitches_2026.parquet from Step 1)
"""
from __future__ import annotations

import sys

import pandas as pd

from src.config import OUT_TABLES, PITCHES_PARQUET

COUNTS = [f"{b}-{s}" for b in range(4) for s in range(3)]
COUNT_ORDER = ["All"] + COUNTS
DROP_TYPES = {"PO", "IN", "EP", "AB", "UN", "FA"}  # pitchouts, intentional balls, eephus, unknown


def mix_by_count(pitches: pd.DataFrame, pitcher_ids=None) -> pd.DataFrame:
    """pitches: Statcast rows with pitcher, stand, balls, strikes, pitch_type (and is_relief if present)."""
    p = pitches
    if "is_relief" in p.columns:
        p = p[p["is_relief"]]
    if pitcher_ids is not None:
        p = p[p["pitcher"].isin(set(pitcher_ids))]
    p = p[p["pitch_type"].notna() & ~p["pitch_type"].isin(DROP_TYPES)]
    p = p[p["balls"].between(0, 3) & p["strikes"].between(0, 2)]
    p = p.assign(count=p["balls"].astype(int).astype(str) + "-" + p["strikes"].astype(int).astype(str))
    both = pd.concat([p, p.assign(stand="All")])
    by = both.groupby(["pitcher", "stand", "count", "pitch_type"]).size().rename("n").reset_index()
    allc = both.groupby(["pitcher", "stand", "pitch_type"]).size().rename("n").reset_index().assign(count="All")
    out = pd.concat([by, allc], ignore_index=True)
    denom = out.groupby(["pitcher", "stand", "count"])["n"].transform("sum")
    out["count_n"] = denom
    out["usage_pct"] = (100 * out["n"] / denom).round(1)
    return out.sort_values(["pitcher", "stand", "count", "n"], ascending=[True, True, True, False])


def main() -> int:
    pitches = pd.read_parquet(PITCHES_PARQUET, columns=["pitcher", "stand", "balls", "strikes", "pitch_type",
                                                         "is_relief"])
    out = mix_by_count(pitches)
    path = OUT_TABLES / "pitch_mix_by_count.csv"
    out.to_csv(path, index=False)
    print(f"wrote {path} ({len(out):,} rows, {out['pitcher'].nunique()} relievers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
