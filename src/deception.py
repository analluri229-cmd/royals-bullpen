"""Step 5A (Core): delivery consistency and tunneling, using arm angle and release.

Delivery (not in the video): the same release point, arm slot and extension
on every pitch, so nothing tips the pitch. This is the prerequisite for tunneling.
  - Per pitcher x pitch type: SD of release side, release height, extension
    and arm angle, plus the gap between that pitch's mean release and the
    primary fastball's.
  - How often: share of all his pitches released within 2 inches of his
    primary fastball's mean release point.
  - Percentiles: 100 = tightest / smallest gap (better), against qualified
    relievers with the same hand.

Tunneling (pattern 2): two different pitch types thrown back to back in a PA.
Each trajectory is rebuilt from Statcast's 9-parameter fit and compared at
the decision point (23.8 ft from the plate by default, also 20 and 25 ft)
and at the front of the plate.
  - tunnel_in = distance between the two pitches at the decision point (inches)
  - plate_in = distance between them at the plate (inches)
  - break_tunnel_ratio = plate_in / tunnel_in (higher = better)
  - A pair "tunnels" when tunnel_in is below the league median for that pitch
    pair (e.g. FF->SL) and hand.
  - How well: Whiff% and Chase% on the second pitch of tunneled vs other pairs.

Usage:  python -m src.deception
Outputs: outputs/tables/delivery_by_pitcher.csv, tunnel_by_pitcher.csv,
         sequence_pairs.csv (KC pairs), sequencing_by_pitcher.csv (long format)
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.config import KC, OUT_TABLES
from src.stuff import EXCLUDE_PITCH_TYPES, PITCH_GROUPS, PLATE_FRONT_Y, START_Y

TUNNEL_FT = 23.8
TUNNEL_TEST_FT = (20.0, 25.0)
RELEASE_RADIUS_IN = 2.0
MIN_PATTERN_PITCHES = 25

SWING = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "foul_bunt",
         "hit_into_play", "missed_bunt", "bunt_foul_tip"}
WHIFF = {"swinging_strike", "swinging_strike_blocked", "foul_tip", "missed_bunt"}


# ---------------------------------------------------------------- shared

def valid(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["pitch_type"].notna() & ~df["pitch_type"].isin(EXCLUDE_PITCH_TYPES)]


def primary_fastball(df: pd.DataFrame) -> pd.Series:
    """Most-used FF/SI/FC per pitcher."""
    fb = df[df["pitch_type"].map(PITCH_GROUPS).eq("FB")]
    counts = fb.groupby(["pitcher", "pitch_type"]).size().rename("n").reset_index()
    return counts.sort_values("n", ascending=False).drop_duplicates("pitcher").set_index("pitcher")["pitch_type"]


def good_pctile(values: pd.Series, pool: np.ndarray) -> np.ndarray:
    """Percentile where 100 = smallest value in the pool (mid-rank for ties)."""
    pool = np.sort(pool[~np.isnan(pool)])
    v = values.to_numpy(dtype=float)
    if len(pool) == 0:
        return np.full(len(v), np.nan)
    lo = np.searchsorted(pool, v, side="left")
    hi = np.searchsorted(pool, v, side="right")
    pct = 100 - 100 * (lo + hi) / 2 / len(pool)
    return np.where(np.isnan(v), np.nan, pct.round(1))


def add_good_pctiles(tab, cols, qualified_ids, by=("throws",), min_col="n_pitches",
                     min_n=MIN_PATTERN_PITCHES):
    tab = tab.copy()
    ok = tab[min_col] >= min_n
    ref = tab[ok & tab["pitcher"].isin(set(qualified_ids))]
    for c in cols:
        tab[f"{c}_pctile"] = np.nan
        for key, g in tab[ok].groupby(list(by)):
            key = key if isinstance(key, tuple) else (key,)
            mask = np.logical_and.reduce([ref[b] == k for b, k in zip(by, key)])
            tab.loc[g.index, f"{c}_pctile"] = good_pctile(g[c], ref.loc[mask, c].to_numpy(dtype=float))
    return tab


# ---------------------------------------------------------------- delivery

def delivery(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (by pitch type, by pitcher). Positions in inches, arm angle in degrees."""
    df = valid(df).dropna(subset=["release_pos_x", "release_pos_z"]).copy()
    df["rx_in"] = df["release_pos_x"] * 12
    df["rz_in"] = df["release_pos_z"] * 12
    df["ext_in"] = df["release_extension"] * 12
    by_type = df.groupby(["pitcher", "pitch_type"]).agg(
        name=("player_name", "first"), throws=("p_throws", "first"), n_pitches=("rx_in", "size"),
        rx_mean=("rx_in", "mean"), rz_mean=("rz_in", "mean"), ext_mean=("ext_in", "mean"),
        arm_mean=("arm_angle", "mean"), sd_side_in=("rx_in", "std"), sd_height_in=("rz_in", "std"),
        sd_ext_in=("ext_in", "std"), sd_arm_deg=("arm_angle", "std")).reset_index()

    fb = primary_fastball(df).rename("primary_fb")
    by_type = by_type.join(fb, on="pitcher")
    ref = by_type[by_type["pitch_type"] == by_type["primary_fb"]].set_index("pitcher")[
        ["rx_mean", "rz_mean", "ext_mean", "arm_mean"]].add_prefix("fb_")
    by_type = by_type.join(ref, on="pitcher")
    by_type["gap_side_in"] = (by_type["rx_mean"] - by_type["fb_rx_mean"]).abs()
    by_type["gap_height_in"] = (by_type["rz_mean"] - by_type["fb_rz_mean"]).abs()
    by_type["release_gap_in"] = np.hypot(by_type["gap_side_in"], by_type["gap_height_in"])
    by_type["gap_ext_in"] = (by_type["ext_mean"] - by_type["fb_ext_mean"]).abs()
    by_type["gap_arm_deg"] = (by_type["arm_mean"] - by_type["fb_arm_mean"]).abs()
    by_type["is_primary_fb"] = by_type["pitch_type"].eq(by_type["primary_fb"])

    df = df.join(ref, on="pitcher")
    df["dist_fb_in"] = np.hypot(df["rx_in"] - df["fb_rx_mean"], df["rz_in"] - df["fb_rz_mean"])
    df["within"] = df["dist_fb_in"] <= RELEASE_RADIUS_IN
    secondary = by_type[~by_type["is_primary_fb"]]
    w = secondary.assign(wgap=secondary["release_gap_in"] * secondary["n_pitches"])
    sec = w.groupby("pitcher").agg(sec_n=("n_pitches", "sum"), wgap=("wgap", "sum"),
                                   max_release_gap_in=("release_gap_in", "max"))
    by_pitcher = df.groupby("pitcher").agg(
        name=("player_name", "first"), throws=("p_throws", "first"), n_pitches=("rx_in", "size"),
        within_2in_pct=("within", "mean"), sd_side_in=("rx_in", "std"), sd_height_in=("rz_in", "std"),
        sd_arm_deg=("arm_angle", "std")).join(fb).join(sec)
    by_pitcher["within_2in_pct"] = (100 * by_pitcher["within_2in_pct"]).round(1)
    by_pitcher["avg_release_gap_in"] = by_pitcher["wgap"] / by_pitcher["sec_n"]
    by_pitcher["avg_arm_gap_deg"] = by_pitcher.index.map(
        secondary.assign(w=secondary["gap_arm_deg"] * secondary["n_pitches"]).groupby("pitcher")["w"].sum()
        / secondary.groupby("pitcher")["n_pitches"].sum())
    by_pitcher = by_pitcher.drop(columns=["wgap", "sec_n"]).reset_index()
    return by_type, by_pitcher


# ---------------------------------------------------------------- trajectories

def position_at(df: pd.DataFrame, y: float) -> tuple[np.ndarray, np.ndarray]:
    """(x, z) in feet when the pitch crosses distance y from the plate.

    Statcast's fit starts at y = 50 ft but doesn't give x/z there, so they are
    back-solved from plate_x / plate_z at the front of the plate.
    """
    vx0, vy0, vz0 = (df[c].to_numpy(float) for c in ("vx0", "vy0", "vz0"))
    ax, ay, az = (df[c].to_numpy(float) for c in ("ax", "ay", "az"))

    def t_at(yy):
        # 50 + vy0 t + ay t^2 / 2 = yy, take the first crossing (vy0 < 0)
        a, b, c = ay / 2, vy0, START_Y - yy
        return (-b - np.sqrt(b * b - 4 * a * c)) / (2 * a)

    tp = t_at(PLATE_FRONT_Y)
    x0 = df["plate_x"].to_numpy(float) - vx0 * tp - ax * tp ** 2 / 2
    z0 = df["plate_z"].to_numpy(float) - vz0 * tp - az * tp ** 2 / 2
    t = t_at(y)
    return x0 + vx0 * t + ax * t ** 2 / 2, z0 + vz0 * t + az * t ** 2 / 2


def build_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Back-to-back pitches of different types by the same pitcher in one PA."""
    df = valid(df).dropna(subset=["vx0", "vy0", "vz0", "ax", "ay", "az", "plate_x", "plate_z"])
    df = df.sort_values(["game_pk", "at_bat_number", "pitch_number"]).reset_index(drop=True)
    cols = {"tunnel": TUNNEL_FT, **{f"t{int(f)}": f for f in TUNNEL_TEST_FT}, "plate": PLATE_FRONT_Y}
    for k, y in cols.items():
        df[f"x_{k}"], df[f"z_{k}"] = position_at(df, y)
    prev = df.groupby(["game_pk", "at_bat_number"]).shift(1)
    same = (prev["pitcher"].eq(df["pitcher"]) & (df["pitch_number"] - prev["pitch_number"]).eq(1)
            & prev["pitch_type"].notna() & prev["pitch_type"].ne(df["pitch_type"]))
    p = df[same].copy()
    q = prev[same]
    p["prev_type"] = q["pitch_type"]
    p["pair"] = p["prev_type"] + "->" + p["pitch_type"]
    for k in cols:
        p[f"{k}_in"] = 12 * np.hypot(p[f"x_{k}"] - q[f"x_{k}"], p[f"z_{k}"] - q[f"z_{k}"])
    p["break_tunnel_ratio"] = p["plate_in"] / p["tunnel_in"].clip(lower=0.5)
    desc = p["description"].astype("string")
    p["swing"] = desc.isin(SWING)
    p["whiff"] = desc.isin(WHIFF)
    p["out_of_zone"] = pd.to_numeric(p["zone"], errors="coerce") > 9
    keep = ["game_pk", "at_bat_number", "pitch_number", "pitcher", "player_name", "p_throws",
            "stand", "pair", "prev_type", "pitch_type", "tunnel_in", "t20_in", "t25_in", "plate_in",
            "break_tunnel_ratio", "swing", "whiff", "out_of_zone", "description"]
    return p[[c for c in keep if c in p.columns]].reset_index(drop=True)


def flag_tunneled(pairs: pd.DataFrame) -> pd.DataFrame:
    med = pairs.groupby(["pair", "p_throws"])["tunnel_in"].transform("median")
    return pairs.assign(league_median_tunnel_in=med, tunneled=pairs["tunnel_in"] < med)


def rates(g: pd.DataFrame) -> pd.Series:
    sw = g["swing"].sum()
    ooz = g["out_of_zone"].sum()
    return pd.Series({"n": len(g), "whiff_pct": 100 * g["whiff"].sum() / sw if sw else np.nan,
                      "chase_pct": 100 * (g["swing"] & g["out_of_zone"]).sum() / ooz if ooz else np.nan})


def tunnel_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    """Per pitcher x pitch pair."""
    g = pairs.groupby(["pitcher", "pair"])
    out = g.agg(name=("player_name", "first"), throws=("p_throws", "first"), n_pairs=("tunnel_in", "size"),
                tunnel_in=("tunnel_in", "median"), tunnel_20ft_in=("t20_in", "median"),
                tunnel_25ft_in=("t25_in", "median"), plate_in=("plate_in", "median"),
                break_tunnel_ratio=("break_tunnel_ratio", "median"),
                tunnel_rate=("tunneled", "mean")).reset_index()
    out["tunnel_rate"] = (100 * out["tunnel_rate"]).round(1)
    t = pairs[pairs["tunneled"]].groupby(["pitcher", "pair"]).apply(rates, include_groups=False)
    n = pairs[~pairs["tunneled"]].groupby(["pitcher", "pair"]).apply(rates, include_groups=False)
    out = out.join(t.add_prefix("tun_"), on=["pitcher", "pair"]).join(n.add_prefix("non_"), on=["pitcher", "pair"])
    out["whiff_lift"] = out["tun_whiff_pct"] - out["non_whiff_pct"]
    out["chase_lift"] = out["tun_chase_pct"] - out["non_chase_pct"]
    out["sample_flag"] = np.where(out["n_pairs"] >= MIN_PATTERN_PITCHES, "", "small sample")
    return out


def pitcher_tunnel(pairs: pd.DataFrame) -> pd.DataFrame:
    """One row per pitcher across all his pairs (for the long-format readout)."""
    g = pairs.groupby("pitcher")
    out = g.agg(name=("player_name", "first"), throws=("p_throws", "first"),
                opportunities=("tunnel_in", "size"), uses=("tunneled", "sum"),
                tunnel_in=("tunnel_in", "median"), break_tunnel_ratio=("break_tunnel_ratio", "median"))
    t = pairs[pairs["tunneled"]].groupby("pitcher").apply(rates, include_groups=False)
    n = pairs[~pairs["tunneled"]].groupby("pitcher").apply(rates, include_groups=False)
    out = out.join(t.add_prefix("tun_")).join(n.add_prefix("non_")).reset_index()
    out["usage_rate"] = 100 * out["uses"] / out["opportunities"]
    return out


# ---------------------------------------------------------------- long format

def raw_pctile(values: pd.Series, pool: pd.Series) -> np.ndarray:
    pool = np.sort(pool.dropna().to_numpy(float))
    v = values.to_numpy(float)
    if len(pool) == 0:
        return np.full(len(v), np.nan)
    lo, hi = np.searchsorted(pool, v, "left"), np.searchsorted(pool, v, "right")
    return np.where(np.isnan(v), np.nan, (100 * (lo + hi) / 2 / len(pool)).round(1))


def long_rows(deliv_p: pd.DataFrame, tun_p: pd.DataFrame, qualified_ids, kc_ids) -> pd.DataFrame:
    q = set(qualified_ids)
    rows = []
    d = deliv_p.copy()
    ref = d[d["pitcher"].isin(q)]
    d["usage_pctile"] = raw_pctile(d["within_2in_pct"], ref["within_2in_pct"])
    d["lift_pctile"] = 100 - raw_pctile(d["avg_release_gap_in"], ref["avg_release_gap_in"])
    rows.append(pd.DataFrame({
        "pitcher_id": d["pitcher"], "name": d["name"], "pattern": "delivery",
        "opportunities": d["n_pitches"], "uses": (d["within_2in_pct"] / 100 * d["n_pitches"]).round(),
        "usage_rate": d["within_2in_pct"], "usage_pctile": d["usage_pctile"],
        "outcome_metric": "avg_release_gap_in (secondary vs FB, lower = better)",
        "pattern_value": d["avg_release_gap_in"].round(2), "baseline_value": np.nan, "lift": np.nan,
        "lift_pctile": d["lift_pctile"], "n_pitches": d["n_pitches"]}))
    for metric in ("whiff_pct", "chase_pct"):
        t = tun_p.copy()
        t["lift"] = t[f"tun_{metric}"] - t[f"non_{metric}"]
        ref = t[t["pitcher"].isin(q) & (t["uses"] >= MIN_PATTERN_PITCHES)]
        rows.append(pd.DataFrame({
            "pitcher_id": t["pitcher"], "name": t["name"], "pattern": "tunneling",
            "opportunities": t["opportunities"], "uses": t["uses"], "usage_rate": t["usage_rate"].round(1),
            "usage_pctile": raw_pctile(t["usage_rate"], ref["usage_rate"]),
            "outcome_metric": metric, "pattern_value": t[f"tun_{metric}"].round(1),
            "baseline_value": t[f"non_{metric}"].round(1), "lift": t["lift"].round(1),
            "lift_pctile": raw_pctile(t["lift"], ref["lift"]), "n_pitches": t["uses"]}))
    out = pd.concat(rows, ignore_index=True)
    out.insert(2, "group", np.where(out["pitcher_id"].isin(set(kc_ids)), "KC reliever", "MLB reliever"))
    out["sample_flag"] = np.where(out["n_pitches"] >= MIN_PATTERN_PITCHES, "", "small sample")
    return out


# ---------------------------------------------------------------- main

def build(relief: pd.DataFrame, qualified_ids, kc_ids):
    by_type, by_pitcher = delivery(relief)
    by_type = add_good_pctiles(by_type, ["sd_side_in", "sd_height_in", "sd_ext_in", "sd_arm_deg",
                                         "release_gap_in", "gap_arm_deg"], qualified_ids,
                               by=("pitch_type", "throws"), min_n=50)
    by_pitcher = add_good_pctiles(by_pitcher, ["sd_arm_deg", "avg_release_gap_in", "avg_arm_gap_deg"],
                                  qualified_ids, by=("throws",), min_n=300)
    by_pitcher["within_2in_pctile"] = 100 - add_good_pctiles(
        by_pitcher.assign(x=by_pitcher["within_2in_pct"]), ["x"], qualified_ids, min_n=300)["x_pctile"]
    pairs = flag_tunneled(build_pairs(relief))
    tun = tunnel_summary(pairs)
    tun = add_good_pctiles(tun, ["tunnel_in"], qualified_ids, by=("pair", "throws"), min_col="n_pairs")
    ratio_ref = tun[(tun["n_pairs"] >= MIN_PATTERN_PITCHES) & tun["pitcher"].isin(set(qualified_ids))]
    tun["break_tunnel_ratio_pctile"] = np.nan
    for key, g in tun[tun["n_pairs"] >= MIN_PATTERN_PITCHES].groupby(["pair", "throws"]):
        pool = ratio_ref.loc[(ratio_ref["pair"] == key[0]) & (ratio_ref["throws"] == key[1]), "break_tunnel_ratio"]
        tun.loc[g.index, "break_tunnel_ratio_pctile"] = raw_pctile(g["break_tunnel_ratio"], pool)
    long = long_rows(by_pitcher, pitcher_tunnel(pairs), qualified_ids, kc_ids)
    for t in (by_type, by_pitcher, tun):
        t.insert(2, "group", np.where(t["pitcher"].isin(set(kc_ids)), "KC reliever", "MLB reliever"))
    return by_type.round(2), by_pitcher.round(2), tun.round(2), pairs, long


def main() -> int:
    from src.config import PITCHES_PARQUET
    pitches = pd.read_parquet(PITCHES_PARQUET)
    league = pd.read_csv(OUT_TABLES / "league_relievers_2026.csv")
    kc_ids = set(pd.read_csv(OUT_TABLES / "kc_relievers_2026.csv")["pitcher"])
    relief = pitches[pitches["is_relief"] & (~pitches["pitcher"].isin(kc_ids) | pitches["pitching_team"].eq(KC))]
    run(relief, league.loc[league["qualified"], "pitcher"], kc_ids)
    return 0


def run(relief, qualified_ids, kc_ids) -> None:
    by_type, by_pitcher, tun, pairs, long = build(relief, qualified_ids, kc_ids)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    by_type.to_csv(OUT_TABLES / "delivery_by_pitch.csv", index=False)
    by_pitcher.to_csv(OUT_TABLES / "delivery_by_pitcher.csv", index=False)
    tun.to_csv(OUT_TABLES / "tunnel_by_pitcher.csv", index=False)
    pairs[pairs["pitcher"].isin(kc_ids)].round(2).to_csv(OUT_TABLES / "sequence_pairs.csv", index=False)
    long.to_csv(OUT_TABLES / "sequencing_by_pitcher.csv", index=False)
    kc = by_pitcher[by_pitcher["group"] == "KC reliever"].sort_values("n_pitches", ascending=False)
    pd.set_option("display.width", 250)
    print(kc[["name", "n_pitches", "primary_fb", "within_2in_pct", "avg_release_gap_in", "avg_arm_gap_deg",
              "sd_arm_deg", "within_2in_pctile", "avg_release_gap_in_pctile", "sd_arm_deg_pctile"]].to_string(index=False))
    print(f"pairs: {len(pairs):,} league, {pairs.pitcher.isin(kc_ids).sum():,} KC")


if __name__ == "__main__":
    sys.exit(main())
