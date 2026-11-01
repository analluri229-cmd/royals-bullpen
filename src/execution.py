"""Step 5: Execution metrics per reliever (relief pitches only).

Per reliever, each with a league percentile (raw, 100 = highest value; Step 6
inverts BB% and decides direction):
  Zone%      pitches in Statcast zones 1-9 / pitches with a zone
  F-Strike%  PAs whose first pitch is a strike or ball in play (type S or X)
  3PS%       PAs reaching two strikes within the first three pitches, or
             ending in an out within three pitches
  Kill%      strikeouts / PAs that reach a two-strike count
  K%, BB%    per PA (BB% includes intentional walks, as FanGraphs does)
  Whiff%     whiffs / swings
  Chase%     swings at pitches outside the zone / pitches outside the zone
  CSW%       (called strikes + whiffs) / pitches
  Location+  from the manual FanGraphs export, joined by name

Count plans (execution_by_count.csv): Zone% and pitch usage by count state
(ahead, even, behind, two strikes) and batter hand.
Mixing: pitch-usage entropy (bits) by count state, and the top pitch's share
with two strikes.
Sequencing: back-to-back same-pitch rate, and the most common two-pitch
sequences with Whiff% on the second pitch (sequence_summary.csv).

Usage:  python -m src.execution
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.config import KC, OUT_TABLES
from src.relievers import EVENT_OUTS
from src.stuff import EXCLUDE_PITCH_TYPES, name_key

SWING = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "foul_bunt",
         "hit_into_play", "missed_bunt", "bunt_foul_tip"}
WHIFF = {"swinging_strike", "swinging_strike_blocked", "foul_tip", "missed_bunt"}
CALLED = {"called_strike"}
K_EVENTS = {"strikeout", "strikeout_double_play"}
BB_EVENTS = {"walk", "intent_walk"}
# Not a plate appearance for the batter (runner outs end the inning mid-PA).
NON_PA_EVENTS = {"caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
                 "pickoff_1b", "pickoff_2b", "pickoff_3b", "pickoff_caught_stealing_2b",
                 "pickoff_caught_stealing_3b", "pickoff_caught_stealing_home", "other_out",
                 "stolen_base_2b", "wild_pitch", "passed_ball", "game_advisory"}
MIN_PA = 50

PCTILE = ["zone_pct", "f_strike_pct", "three_ps_pct", "kill_pct", "k_pct", "bb_pct",
          "k_bb_pct", "whiff_pct", "chase_pct", "csw_pct", "location_plus"]


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    d = df["description"].astype("string")
    z = pd.to_numeric(df["zone"], errors="coerce")
    df["in_zone"] = z.between(1, 9)
    df["has_zone"] = z.notna()
    df["swing"] = d.isin(SWING)
    df["whiff"] = d.isin(WHIFF)
    df["called"] = d.isin(CALLED)
    df["chase"] = df["swing"] & ~df["in_zone"] & df["has_zone"]
    df["ooz"] = ~df["in_zone"] & df["has_zone"]
    df["strike_type"] = df["type"].astype("string").isin(["S", "X"])
    b, s = df["balls"], df["strikes"]
    df["count_state"] = np.select([s == 2, s > b, s == b], ["two_strikes", "ahead", "even"], "behind")
    return df


def pa_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per plate appearance, credited to the pitcher of its last pitch."""
    df = df.sort_values(["game_pk", "at_bat_number", "pitch_number"])
    g = df.groupby(["game_pk", "at_bat_number"])
    pa = g.agg(pitcher=("pitcher", "last"), events=("events", "last"), last_num=("pitch_number", "max"),
               first_strike=("strike_type", "first"))
    two = df[df["strikes"] == 2].groupby(["game_pk", "at_bat_number"])["pitch_number"].min()
    pa["first_two_strike_pitch"] = two  # pitch number thrown at 2 strikes (pre-pitch count)
    pa = pa[pa["events"].notna() & ~pa["events"].isin(NON_PA_EVENTS)].copy()
    ev = pa["events"].astype("string")
    pa["k"] = ev.isin(K_EVENTS)
    pa["bb"] = ev.isin(BB_EVENTS)
    pa["out"] = ev.map(EVENT_OUTS).fillna(0) > 0
    pa["reached_two"] = pa["first_two_strike_pitch"].notna() | pa["k"]
    # two strikes after <= 3 pitches means the 4th pitch (or earlier) is thrown at 2 strikes
    pa["three_ps"] = (pa["first_two_strike_pitch"] <= 4) | (pa["out"] & (pa["last_num"] <= 3)) | (
        pa["k"] & (pa["last_num"] <= 3))
    return pa.reset_index()


def pitcher_rates(df: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    p = df.groupby("pitcher").agg(
        name=("player_name", "first"), throws=("p_throws", "first"), n_pitches=("swing", "size"),
        zone_n=("has_zone", "sum"), in_zone=("in_zone", "sum"), swings=("swing", "sum"),
        whiffs=("whiff", "sum"), called=("called", "sum"), chases=("chase", "sum"), ooz=("ooz", "sum"))
    a = pa.groupby("pitcher").agg(pa=("k", "size"), k=("k", "sum"), bb=("bb", "sum"),
                                  f_strike=("first_strike", "sum"), three_ps=("three_ps", "sum"),
                                  two_strike_pa=("reached_two", "sum"))
    p = p.join(a)
    div = lambda n, d: (100 * n / d.replace(0, np.nan)).round(1)  # noqa: E731
    p["zone_pct"] = div(p["in_zone"], p["zone_n"])
    p["f_strike_pct"] = div(p["f_strike"], p["pa"])
    p["three_ps_pct"] = div(p["three_ps"], p["pa"])
    p["kill_pct"] = div(p["k"], p["two_strike_pa"])
    p["k_pct"] = div(p["k"], p["pa"])
    p["bb_pct"] = div(p["bb"], p["pa"])
    p["k_bb_pct"] = (p["k_pct"] - p["bb_pct"]).round(1)
    p["whiff_pct"] = div(p["whiffs"], p["swings"])
    p["chase_pct"] = div(p["chases"], p["ooz"])
    p["csw_pct"] = div(p["called"] + p["whiffs"], p["n_pitches"])
    return p.reset_index()


def entropy_bits(counts: pd.Series) -> float:
    p = counts / counts.sum()
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def mixing(df: pd.DataFrame) -> pd.DataFrame:
    by_state = (df.groupby(["pitcher", "count_state", "pitch_type"]).size()
                  .groupby(["pitcher", "count_state"]).apply(entropy_bits).unstack())
    by_state.columns = [f"entropy_{c}" for c in by_state.columns]
    two = df[df["count_state"] == "two_strikes"]
    top = two.groupby(["pitcher", "pitch_type"]).size().rename("n").reset_index()
    top["share"] = top["n"] / top.groupby("pitcher")["n"].transform("sum")
    top = top.sort_values("share", ascending=False).drop_duplicates("pitcher").set_index("pitcher")
    out = by_state.join(top[["pitch_type", "share"]].rename(
        columns={"pitch_type": "two_strike_top_pitch", "share": "two_strike_top_share"}))
    out["two_strike_top_share"] = (100 * out["two_strike_top_share"]).round(1)
    return out.round(2).reset_index()


def sequences(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values(["game_pk", "at_bat_number", "pitch_number"])
    prev = df.groupby(["game_pk", "at_bat_number"])[["pitcher", "pitch_type", "pitch_number"]].shift(1)
    ok = prev["pitcher"].eq(df["pitcher"]) & (df["pitch_number"] - prev["pitch_number"]).eq(1)
    s = df[ok].assign(prev_type=prev.loc[ok, "pitch_type"])
    s["repeat"] = s["prev_type"].eq(s["pitch_type"])
    s["seq"] = s["prev_type"] + "->" + s["pitch_type"]
    rep = s.groupby("pitcher")["repeat"].mean().mul(100).round(1).rename("back_to_back_same_pct")
    summ = s.groupby(["pitcher", "seq"]).agg(n=("swing", "size"), swings=("swing", "sum"),
                                             whiffs=("whiff", "sum")).reset_index()
    summ["share_pct"] = (100 * summ["n"] / summ.groupby("pitcher")["n"].transform("sum")).round(1)
    summ["whiff_pct_2nd"] = (100 * summ["whiffs"] / summ["swings"].replace(0, np.nan)).round(1)
    summ["rank"] = summ.groupby("pitcher")["n"].rank(method="first", ascending=False).astype(int)
    summ = summ.sort_values(["pitcher", "rank"])
    top3 = summ[summ["rank"] <= 3].pivot(index="pitcher", columns="rank", values="seq")
    top3.columns = [f"top_seq_{c}" for c in top3.columns]
    return rep.to_frame().join(top3).reset_index(), summ


def count_plans(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["pitcher", "count_state", "stand"])
    zone = g.agg(n=("in_zone", "size"), zone_pct=("in_zone", "mean")).reset_index()
    zone["zone_pct"] = (100 * zone["zone_pct"]).round(1)
    use = (df.groupby(["pitcher", "count_state", "stand", "pitch_type"]).size()
             .rename("n_type").reset_index())
    use = use.merge(zone[["pitcher", "count_state", "stand", "n"]], on=["pitcher", "count_state", "stand"])
    use["usage_pct"] = (100 * use["n_type"] / use["n"]).round(1)
    wide = use.pivot_table(index=["pitcher", "count_state", "stand"], columns="pitch_type",
                           values="usage_pct", fill_value=0).add_prefix("usage_").reset_index()
    return zone.merge(wide, on=["pitcher", "count_state", "stand"])


def location_plus(fg: pd.DataFrame | None) -> pd.DataFrame:
    if fg is None or "Name" not in fg.columns:
        return pd.DataFrame(columns=["name_key", "location_plus"])
    col = next((c for c in fg.columns if str(c).strip() in ("Location+", "Loc+")), None)
    if col is None:
        return pd.DataFrame(columns=["name_key", "location_plus"])
    return pd.DataFrame({"name_key": fg["Name"].map(name_key),
                         "location_plus": pd.to_numeric(fg[col], errors="coerce")}).drop_duplicates("name_key")


def raw_pctiles(tab: pd.DataFrame, cols, qualified_ids) -> pd.DataFrame:
    tab = tab.copy()
    ok = tab["pa"] >= MIN_PA
    ref = tab[ok & tab["pitcher"].isin(set(qualified_ids))]
    for c in cols:
        if c not in tab:
            continue
        pool = np.sort(ref[c].dropna().to_numpy(float))
        v = tab[c].to_numpy(float)
        lo, hi = np.searchsorted(pool, v, "left"), np.searchsorted(pool, v, "right")
        pct = np.where(np.isnan(v) | ~ok.to_numpy() | (len(pool) == 0), np.nan,
                       (100 * (lo + hi) / 2 / max(len(pool), 1)).round(1))
        tab[f"{c}_pctile"] = pct
    return tab


def build(relief: pd.DataFrame, qualified_ids, kc_ids, fg=None):
    df = add_flags(relief)  # rates use every pitch; mix and sequences drop non-pitch codes
    pa = pa_table(df)
    tab = pitcher_rates(df, pa)
    mixed = df[df["pitch_type"].notna() & ~df["pitch_type"].isin(EXCLUDE_PITCH_TYPES)]
    tab = tab.merge(mixing(mixed), on="pitcher", how="left")
    seq, summ = sequences(mixed)
    tab = tab.merge(seq, on="pitcher", how="left")
    tab["name_key"] = tab["name"].map(name_key)
    tab = tab.merge(location_plus(fg), on="name_key", how="left").drop(columns="name_key")
    tab = raw_pctiles(tab, PCTILE, qualified_ids)
    tab["sample_flag"] = np.where(tab["pa"] >= MIN_PA, "", "small sample")
    tab.insert(2, "group", np.where(tab["pitcher"].isin(set(kc_ids)), "KC reliever", "MLB reliever"))
    counts = count_plans(mixed)
    counts.insert(1, "group", np.where(counts["pitcher"].isin(set(kc_ids)), "KC reliever", "MLB reliever"))
    return tab, counts, summ


def run(relief, qualified_ids, kc_ids, fg=None):
    tab, counts, summ = build(relief, qualified_ids, kc_ids, fg)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    tab.to_csv(OUT_TABLES / "execution_by_reliever.csv", index=False)
    counts.to_csv(OUT_TABLES / "execution_by_count.csv", index=False)
    summ[summ["pitcher"].isin(set(kc_ids))].to_csv(OUT_TABLES / "sequence_summary.csv", index=False)
    kc = tab[(tab["group"] == "KC reliever") & tab["sample_flag"].eq("")].sort_values("pa", ascending=False)
    pd.set_option("display.width", 250)
    print(kc[["name", "pa", "zone_pct", "f_strike_pct", "three_ps_pct", "kill_pct", "k_pct", "bb_pct",
              "whiff_pct", "chase_pct", "csw_pct", "location_plus", "back_to_back_same_pct",
              "two_strike_top_pitch", "two_strike_top_share"]].to_string(index=False))
    return tab, counts, summ


def main() -> int:
    from src.config import PITCHES_PARQUET
    from src.fangraphs import load_player_relievers
    pitches = pd.read_parquet(PITCHES_PARQUET)
    league = pd.read_csv(OUT_TABLES / "league_relievers_2026.csv")
    kc_ids = set(pd.read_csv(OUT_TABLES / "kc_relievers_2026.csv")["pitcher"])
    relief = pitches[pitches["is_relief"] & (~pitches["pitcher"].isin(kc_ids) | pitches["pitching_team"].eq(KC))]
    try:
        fg = load_player_relievers(offline=True)
    except FileNotFoundError:
        fg = None
    run(relief, league.loc[league["qualified"], "pitcher"], kc_ids, fg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
