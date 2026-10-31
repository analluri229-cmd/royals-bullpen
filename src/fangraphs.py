"""Step 2: FanGraphs outcome layer (team reliever ranks + player reliever stats).

Each input is tried live first and falls back to a manual CSV export:

  team relievers  FanGraphs leaders API (stats=rel, team totals)
                  -> data/manual/fg_team_relievers_2026.csv
  player relievers pybaseball.pitching_stats(2026, qual=0)
                  -> data/manual/fg_relievers_2026.csv
  team context    pybaseball.team_batting(2026) for wRC+ and Def
                  -> data/manual/fg_team_context_2026.csv

FanGraphs often blocks scraping and the Claude cloud workspace can't reach it,
so run this on Windows, and export the CSVs by hand if the live pull fails.
Manual team exports: FanGraphs > Leaders > Team Stats > Pitching > Split:
Relievers > 2026 > Export Data. A workbook with one sheet per tab is split into
<name>_<tab>.csv by split_fg_workbooks.py; those tab CSVs are merged here and
take precedence over a single <name>.csv export.

Output: outputs/tables/team_bullpen_ranks_2026.csv (prints the Royals row).
Usage:  python -m src.fangraphs [--offline]
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from src.config import DATA_MANUAL, DATA_RAW, OUT_TABLES, SEASON

FG_KC = "KCR"
TEAM_REL_MANUAL = DATA_MANUAL / "fg_team_relievers_2026.csv"
PLAYER_REL_MANUAL = DATA_MANUAL / "fg_relievers_2026.csv"
TEAM_CTX_MANUAL = DATA_MANUAL / "fg_team_context_2026.csv"
TEAM_REL_RAW = DATA_RAW / "fg_team_relievers_2026.csv"
PLAYER_REL_RAW = DATA_RAW / "fg_relievers_2026.csv"
TEAM_CTX_RAW = DATA_RAW / "fg_team_context_2026.csv"

# Stat -> True when higher is better (rank 1 = best).
RANK_STATS = {
    "WAR": True, "ERA": False, "FIP": False, "xFIP": False, "SIERA": False,
    "K%": True, "BB%": False, "K-BB%": True, "WHIP": False, "HR/9": False,
}
CONTEXT_STATS = {"wRC+": True, "Def": True}
PERCENT_COLS = ("K%", "BB%", "K-BB%")

FG_API = "https://www.fangraphs.com/api/leaders/major-league/data"


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a FanGraphs export: Team column, numeric stats, percents as 0-100."""
    df = df.copy()
    df.columns = [str(c).strip().replace("﻿", "") for c in df.columns]
    for alt in ("TeamName", "TeamNameAbb", "Tm"):
        if "Team" not in df.columns and alt in df.columns:
            df = df.rename(columns={alt: "Team"})
    if "K-BB%" not in df.columns and {"K%", "BB%"} <= set(df.columns):
        df["K-BB%"] = None
    for c in list(RANK_STATS) + list(CONTEXT_STATS):
        if c in df.columns and not pd.api.types.is_numeric_dtype(df[c]):
            df[c] = pd.to_numeric(df[c].astype(str).str.replace("%", "").str.strip(),
                                  errors="coerce")
    for c in PERCENT_COLS:
        if c in df.columns and df[c].dropna().abs().max() <= 1.0:
            df[c] = df[c] * 100  # API returns fractions
    if "K-BB%" in df.columns and df["K-BB%"].isna().all():
        df["K-BB%"] = df["K%"] - df["BB%"]
    return df


def rank_teams(df: pd.DataFrame, stats: dict[str, bool]) -> pd.DataFrame:
    """Add <stat>_rank columns, 1 = best, ties share the best rank."""
    df = df.copy()
    for stat, higher_better in stats.items():
        if stat in df.columns:
            df[f"{stat}_rank"] = (df[stat].rank(ascending=not higher_better, method="min")
                                  .astype("Int64"))
    return df


def merge_tabs(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Join FanGraphs tabs of one leaderboard side by side (Name+Team for players, else Team).

    Columns repeated across tabs (ERA, IP, '#', ...) are kept from the first tab only.
    """
    keys = ["Name", "Team"] if "Name" in frames[0].columns else ["Team"]
    out = frames[0]
    for df in frames[1:]:
        new = keys + [c for c in df.columns if c not in out.columns]
        out = out.merge(df[new], on=keys, how="outer", validate="one_to_one")
    return out


def _manual_tabs(manual):
    tabs = sorted(manual.parent.glob(f"{manual.stem}_*.csv"))
    return tabs or ([manual] if manual.exists() else [])


def _cached(raw, live_fn, manual, offline: bool) -> pd.DataFrame:
    if raw.exists():
        return pd.read_csv(raw)
    if not offline:
        try:
            df = live_fn()
            if df is not None and len(df):
                raw.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(raw, index=False)
                return df
        except Exception as e:  # noqa: BLE001 - any scrape failure falls back
            print(f"live pull failed ({type(e).__name__}: {e}); using {manual.name}")
    tabs = _manual_tabs(manual)
    if tabs:
        print(f"manual: {', '.join(p.name for p in tabs)}")
        return merge_tabs([pd.read_csv(p) for p in tabs])
    raise FileNotFoundError(f"No live data and no manual export at {manual}")


def _live_team_relievers() -> pd.DataFrame:
    import requests
    params = {"pos": "all", "stats": "rel", "lg": "all", "qual": 0, "type": 8,
              "season": SEASON, "season1": SEASON, "month": 0, "ind": 0,
              "team": "0,ts", "pageitems": 30, "pagenum": 1}
    r = requests.get(FG_API, params=params, timeout=30,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return pd.DataFrame(r.json()["data"])


def _live_player_relievers() -> pd.DataFrame:
    from pybaseball import pitching_stats
    df = pitching_stats(SEASON, qual=0)
    return df[df["GS"] < df["G"]] if {"GS", "G"} <= set(df.columns) else df


def _live_team_context() -> pd.DataFrame:
    from pybaseball import team_batting
    return team_batting(SEASON)


def load_team_relievers(offline=False):
    return normalize(_cached(TEAM_REL_RAW, _live_team_relievers, TEAM_REL_MANUAL, offline))


def load_player_relievers(offline=False):
    return normalize(_cached(PLAYER_REL_RAW, _live_player_relievers, PLAYER_REL_MANUAL, offline))


def load_team_context(offline=False):
    return normalize(_cached(TEAM_CTX_RAW, _live_team_context, TEAM_CTX_MANUAL, offline))


def build_ranks(offline=False) -> pd.DataFrame:
    team = rank_teams(load_team_relievers(offline), RANK_STATS)
    if len(team) != 30:
        print(f"WARNING: expected 30 teams, got {len(team)}")
    keep = ["Team"] + [c for s in RANK_STATS for c in (s, f"{s}_rank") if c in team.columns]
    out = team[keep]
    try:
        ctx = rank_teams(load_team_context(offline), CONTEXT_STATS)
        ctx_cols = ["Team"] + [c for s in CONTEXT_STATS for c in (s, f"{s}_rank") if c in ctx.columns]
        out = out.merge(ctx[ctx_cols], on="Team", how="left")
    except FileNotFoundError as e:
        print(f"team context skipped: {e}")
    return out.sort_values("WAR_rank" if "WAR_rank" in out else "Team", ignore_index=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="skip live pulls, use manual CSVs")
    a = ap.parse_args(argv)
    ranks = build_ranks(a.offline)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    ranks.to_csv(OUT_TABLES / "team_bullpen_ranks_2026.csv", index=False)
    kc = ranks[ranks["Team"].isin([FG_KC, "KC", "Royals", "Kansas City Royals"])]
    print(kc.T.to_string(header=False) if len(kc) else "Royals row not found; check Team names.")
    try:
        players = load_player_relievers(a.offline)
        print(f"player reliever rows: {len(players)}; "
              f"Stuff+ present: {'Stuff+' in players.columns}")
    except FileNotFoundError as e:
        print(f"player relievers skipped: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
