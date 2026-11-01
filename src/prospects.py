"""Step 7 (prospects): Royals pitching prospects as bullpen options.

Input: data/manual/royals_prospects.csv (FanGraphs The Board: rank, name, age,
highest_level, position, eta, fv). Only pitchers (SP, SIRP, RP) are kept.

Statcast here covers MLB only, so a prospect gets Stuff/Execution scores only if
he pitched in MLB relief in 2026. For everyone else the scores and sequencing
are marked "not available": no AAA tracking export (Part 3 Step 7) and no
FanGraphs minor-league K%/BB% have been loaded yet.

Bullpen timing:
  now      ETA 2026 and already a reliever (SIRP/RP)
  convert  ETA 2026 starter: a possible multi-inning or relief conversion
  later    ETA 2027 or later

Usage:  python -m src.prospects
"""
from __future__ import annotations

import sys

import pandas as pd

from src.config import DATA_MANUAL, OUT_TABLES
from src.stuff import name_key

PITCHER_POS = {"SP", "SIRP", "RP"}
RELIEF_POS = {"SIRP", "RP"}


def bullpen_timing(position: str, eta) -> str:
    try:
        eta = int(eta)
    except (TypeError, ValueError):
        return "unknown"
    if eta <= 2026:
        return "now" if position in RELIEF_POS else "convert"
    return "later"


def fv_number(fv) -> float:
    s = str(fv).strip()
    return float(s.rstrip("+")) + (2.5 if s.endswith("+") else 0.0)


def build(prospects: pd.DataFrame, scores: pd.DataFrame, stuff: pd.DataFrame) -> pd.DataFrame:
    p = prospects[prospects["position"].isin(PITCHER_POS)].copy()
    p["timing"] = [bullpen_timing(a, b) for a, b in zip(p["position"], p["eta"])]
    p["fv_num"] = p["fv"].map(fv_number)
    p["name_key"] = p["name"].map(name_key)
    sc = scores.assign(name_key=scores["name"].map(name_key)).drop(columns="name").drop_duplicates("name_key")
    p = p.merge(sc[["name_key", "pitcher", "qualified", "stuff_score", "execution_score", "quadrant"]],
                on="name_key", how="left")
    mlb_pitches = stuff.assign(name_key=stuff["name"].map(name_key)).groupby("name_key")["n_pitches"].sum()
    p["mlb_2026_pitches"] = p["name_key"].map(mlb_pitches).fillna(0).astype(int)

    def data_status(r):
        if pd.notna(r["stuff_score"]):
            return "MLB 2026 Statcast (scored)"
        if r["mlb_2026_pitches"] > 0:
            return "MLB 2026 Statcast (small sample, not scored)"
        return "no tracking data loaded"
    p["data"] = p.apply(data_status, axis=1)
    p["sequencing"] = p["stuff_score"].notna().map({True: "see sequencing_by_pitcher.csv", False: "not available"})
    order = {"now": 0, "convert": 1, "later": 2, "unknown": 3}
    p = p.sort_values(["timing", "fv_num", "rank"], key=lambda s: s.map(order) if s.name == "timing" else s,
                      ascending=[True, False, True])
    return p.drop(columns="name_key")


def run(prospects, scores, stuff):
    out = build(prospects, scores, stuff)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_TABLES / "prospects_pitchers.csv", index=False)
    pd.set_option("display.width", 250)
    print(out[["rank", "name", "age", "highest_level", "position", "eta", "fv", "timing", "data",
               "stuff_score", "execution_score", "quadrant"]].to_string(index=False))
    return out


def main() -> int:
    run(pd.read_csv(DATA_MANUAL / "royals_prospects.csv"), pd.read_csv(OUT_TABLES / "scores_all_relievers.csv"),
        pd.read_csv(OUT_TABLES / "stuff_by_pitch.csv"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
