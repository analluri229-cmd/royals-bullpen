"""Step 1: pitching team, relief flag, relief IP and the reliever lists.

Definitions (CLAUDE.md, Part 3, Step 1):
- Pitching team: the home team pitches in the top of the inning.
- Relief pitch: any pitch not thrown by the team's first pitcher of that game
  (first pitcher = the pitcher on that team's earliest pitch per game_pk).
- Qualified reliever: at least 20 relief IP or 300 relief pitches.

Usage:  python -m src.relievers
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.config import (KC, MIN_RELIEF_IP, MIN_RELIEF_PITCHES, OUT_TABLES,
                        PITCHES_PARQUET, STATCAST_PARQUET)

# Outs recorded on the play, used only for a game's final half-inning when the
# home team bats (walk-offs end before 3 outs, so the outs-diff method fails).
EVENT_OUTS = {
    "strikeout": 1, "field_out": 1, "force_out": 1, "fielders_choice_out": 1,
    "sac_fly": 1, "sac_bunt": 1, "other_out": 1,
    "caught_stealing_2b": 1, "caught_stealing_3b": 1, "caught_stealing_home": 1,
    "pickoff_1b": 1, "pickoff_2b": 1, "pickoff_3b": 1,
    "pickoff_caught_stealing_2b": 1, "pickoff_caught_stealing_3b": 1,
    "pickoff_caught_stealing_home": 1,
    "double_play": 2, "grounded_into_double_play": 2, "strikeout_double_play": 2,
    "sac_fly_double_play": 2, "sac_bunt_double_play": 2, "triple_play": 3,
}


def add_pitching_team(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    top = df["inning_topbot"].str.lower().eq("top")
    df["pitching_team"] = np.where(top, df["home_team"], df["away_team"])
    df["batting_team"] = np.where(top, df["away_team"], df["home_team"])
    return df


def add_relief_flag(df: pd.DataFrame) -> pd.DataFrame:
    """Needs pitching_team. Adds is_starter_game / is_relief per pitch."""
    df = df.copy()
    order = df.sort_values(["game_pk", "at_bat_number", "pitch_number"])
    first = (order.groupby(["game_pk", "pitching_team"], sort=False)["pitcher"]
             .first().rename("first_pitcher"))
    df = df.join(first, on=["game_pk", "pitching_team"])
    df["is_relief"] = df["pitcher"].ne(df["first_pitcher"])
    return df.drop(columns="first_pitcher")


def pa_outs(df: pd.DataFrame) -> pd.DataFrame:
    """One row per plate appearance with outs recorded during it.

    Outs = next PA's outs_when_up in the same half-inning minus this PA's
    (3 at the end of a half-inning). This also credits outs on caught
    stealing / pickoffs during the PA. For the final half-inning of a game
    when the home team bats, outs come from the event instead.
    """
    pa = (df.sort_values(["game_pk", "at_bat_number", "pitch_number"])
            .groupby(["game_pk", "at_bat_number"], as_index=False)
            .agg(pitcher=("pitcher", "first"), pitching_team=("pitching_team", "first"),
                 is_relief=("is_relief", "first"), inning=("inning", "first"),
                 inning_topbot=("inning_topbot", "first"),
                 outs_when_up=("outs_when_up", "first"), events=("events", "last")))
    pa = pa.sort_values(["game_pk", "at_bat_number"], ignore_index=True)
    half = [pa["game_pk"], pa["inning"], pa["inning_topbot"]]
    nxt = pa.groupby(half)["outs_when_up"].shift(-1)
    pa["outs"] = (nxt.fillna(3) - pa["outs_when_up"]).astype(int)

    last_half = pa.groupby("game_pk")["at_bat_number"].transform("max")
    final_half_id = pa.loc[pa["at_bat_number"].eq(last_half),
                           ["game_pk", "inning", "inning_topbot"]]
    in_final_half = pa.merge(final_half_id.assign(_f=True),
                             on=["game_pk", "inning", "inning_topbot"], how="left")["_f"].eq(True).to_numpy()
    walkoff_half = in_final_half & pa["inning_topbot"].str.lower().eq("bot").to_numpy()
    is_last_pa = nxt.isna().to_numpy()
    fix = walkoff_half & is_last_pa
    pa.loc[fix, "outs"] = pa.loc[fix, "events"].map(EVENT_OUTS).fillna(0).astype(int)
    pa["outs"] = pa["outs"].clip(lower=0)
    return pa


def ip_display(outs: int) -> str:
    return f"{outs // 3}.{outs % 3}"


def summarize_relievers(df: pd.DataFrame, team: str | None = None) -> pd.DataFrame:
    """Relief totals per pitcher (optionally only appearances for `team`)."""
    rel = df[df["is_relief"]]
    if team is not None:
        rel = rel[rel["pitching_team"] == team]
    pa = pa_outs(df)
    pa = pa[pa["is_relief"]]
    if team is not None:
        pa = pa[pa["pitching_team"] == team]

    pitches = rel.groupby("pitcher").agg(
        name=("player_name", "first"), throws=("p_throws", "first"),
        teams=("pitching_team", lambda s: "/".join(sorted(s.dropna().unique()))),
        relief_games=("game_pk", "nunique"), relief_pitches=("pitch_number", "size"))
    outs = pa.groupby("pitcher").agg(relief_outs=("outs", "sum"), relief_bf=("outs", "size"))
    out = pitches.join(outs, how="left").fillna({"relief_outs": 0, "relief_bf": 0})
    out["relief_outs"] = out["relief_outs"].astype(int)
    out["relief_bf"] = out["relief_bf"].astype(int)
    out["relief_ip"] = (out["relief_outs"] / 3).round(3)
    out["relief_ip_display"] = out["relief_outs"].map(ip_display)
    out["qualified"] = (out["relief_ip"] >= MIN_RELIEF_IP) | (out["relief_pitches"] >= MIN_RELIEF_PITCHES)
    out["sample_flag"] = np.where(out["qualified"], "", "small sample")
    return (out.reset_index()
               .sort_values(["qualified", "relief_ip"], ascending=[False, False], ignore_index=True))


def main() -> int:
    df = pd.read_parquet(STATCAST_PARQUET)
    df = add_relief_flag(add_pitching_team(df))
    PITCHES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PITCHES_PARQUET, index=False)

    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    kc = summarize_relievers(df, team=KC)
    league = summarize_relievers(df)
    kc.to_csv(OUT_TABLES / "kc_relievers_2026.csv", index=False)
    league.to_csv(OUT_TABLES / "league_relievers_2026.csv", index=False)

    print(f"relief share of pitches: {df.is_relief.mean():.1%}")
    print(f"league qualified relievers: {league.qualified.sum()} of {len(league)}")
    print(f"KC qualified relievers: {kc.qualified.sum()}; small samples: {(~kc.qualified).sum()}")
    print(kc[["name", "throws", "relief_games", "relief_ip_display", "relief_pitches",
              "relief_bf", "sample_flag"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
