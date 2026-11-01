"""Pitch plinko: how a pitcher's plate appearances travel through the count tree.

Reverse-engineers Baseball Savant's "Pitch Plinko" view from pitch-level Statcast.
Every pitch is one step from its count: a ball moves right, a strike moves down, a
two-strike foul stays, and a PA ends on a ball in play, strikeout, walk or HBP.

Tables:
- outputs/tables/plinko_steps.csv: pitcher x count x step (ball / strike / foul_stay /
  in_play / K / BB / HBP), with n and share of the pitches thrown in that count.
- outputs/tables/plinko_reach.csv: pitcher x count, with PAs that reached that count
  and reach_pct = that ÷ the pitcher's PAs. Count "3-x" = PAs that reached any three-ball count.

Usage:  python -m src.plinko   (needs data/processed/pitches_2026.parquet from Step 1)
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.config import OUT_TABLES, PITCHES_PARQUET

BALLS = {"ball", "blocked_ball", "pitchout", "intent_ball"}
STRIKES = {"called_strike", "swinging_strike", "swinging_strike_blocked", "foul_tip", "missed_bunt",
           "bunt_foul_tip"}
FOULS = {"foul", "foul_pitchout"}
FOUL_BUNT = {"foul_bunt"}
IN_PLAY = {"hit_into_play", "hit_into_play_no_out", "hit_into_play_score"}
STEPS = ["ball", "strike", "foul_stay", "in_play", "K", "BB", "HBP"]
COUNTS = [(b, s) for b in range(4) for s in range(3)]
PA_KEYS = ["game_pk", "at_bat_number"]


def step(description: str, balls: int, strikes: int) -> str | None:
    """Where one pitch sends the PA. None for descriptions we can't place."""
    d = str(description)
    if d in BALLS:
        return "BB" if balls == 3 else "ball"
    if d in STRIKES:
        return "K" if strikes == 2 else "strike"
    if d in FOULS:
        return "foul_stay" if strikes == 2 else "strike"
    if d in FOUL_BUNT:
        return "K" if strikes == 2 else "strike"
    if d in IN_PLAY:
        return "in_play"
    if d == "hit_by_pitch":
        return "HBP"
    return None


def add_steps(pitches: pd.DataFrame) -> pd.DataFrame:
    p = pitches[pitches["balls"].between(0, 3) & pitches["strikes"].between(0, 2)].copy()
    p["step"] = [step(d, b, s) for d, b, s in zip(p["description"], p["balls"], p["strikes"])]
    p = p[p["step"].notna()]
    p["count"] = p["balls"].astype(int).astype(str) + "-" + p["strikes"].astype(int).astype(str)
    return p


def plinko_tables(pitches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = add_steps(pitches)
    steps = p.groupby(["pitcher", "count", "step"]).size().rename("n").reset_index()
    steps["count_n"] = steps.groupby(["pitcher", "count"])["n"].transform("sum")
    steps["share_pct"] = (100 * steps["n"] / steps["count_n"]).round(1)
    pa_counts = p.drop_duplicates(["pitcher", *PA_KEYS, "count"])
    three = pa_counts[pa_counts["balls"] == 3].drop_duplicates(["pitcher", *PA_KEYS]).assign(count="3-x")
    reach = (pd.concat([pa_counts, three]).groupby(["pitcher", "count"]).size().rename("pa_reached")
             .reset_index())
    total = p.drop_duplicates(["pitcher", *PA_KEYS]).groupby("pitcher").size().rename("pa")
    reach = reach.join(total, on="pitcher")
    reach["reach_pct"] = (100 * reach["pa_reached"] / reach["pa"]).round(1)
    return steps, reach


def summary(steps: pd.DataFrame, reach: pd.DataFrame, pitcher: int) -> dict:
    """PA outcome shares and early-count control for one pitcher (used in titles and tests)."""
    s = steps[steps["pitcher"] == pitcher]
    pa = int(reach.loc[reach["pitcher"] == pitcher, "pa"].iloc[0])
    end = s.groupby("step")["n"].sum()
    r = reach[reach["pitcher"] == pitcher].set_index("count")["reach_pct"]
    return {"pa": pa,
            "k_pct": round(100 * end.get("K", 0) / pa, 1),
            "bb_pct": round(100 * end.get("BB", 0) / pa, 1),
            "in_play_pct": round(100 * end.get("in_play", 0) / pa, 1),
            "reach_0_1": float(r.get("0-1", np.nan)), "reach_1_0": float(r.get("1-0", np.nan)),
            "reach_0_2": float(r.get("0-2", np.nan)), "reach_3_x": float(r.get("3-x", 0.0))}


def main() -> int:
    cols = ["pitcher", "game_pk", "at_bat_number", "balls", "strikes", "description", "is_relief"]
    pitches = pd.read_parquet(PITCHES_PARQUET, columns=cols)
    steps, reach = plinko_tables(pitches[pitches["is_relief"]])
    steps.to_csv(OUT_TABLES / "plinko_steps.csv", index=False)
    reach.to_csv(OUT_TABLES / "plinko_reach.csv", index=False)
    print(f"plinko tables: {steps['pitcher'].nunique()} relievers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
