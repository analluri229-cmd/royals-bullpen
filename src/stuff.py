"""Step 4: Stuff metrics per reliever x pitch type, with league percentiles.

Per reliever and pitch type (relief pitches only): usage%, average and max
velocity, IVB and HB (inches), arm angle, release height and side, extension,
VAA, LiVAA and FanGraphs Stuff+ (when the manual export has it).

- VAA is measured at the front of home plate (y = 17/12 ft) with the formula
  in CLAUDE.md, Part 3, Step 4.
- LiVAA: across league relief pitches, regress VAA on plate_z separately for
  fastballs, breaking balls and offspeed, then
  LiVAA = VAA - slope * (plate_z - league mean plate_z).
  (Method still to confirm with the mentor; see Part 5.)
- Percentiles (0-100) compare each value with qualified league relievers who
  throw the same pitch type with the same hand. They are raw percentiles of
  the value (100 = highest), so direction (e.g. flatter VAA = higher) is
  decided in Step 6. Rows under 50 pitches get no percentile and are flagged
  "insufficient sample".

Usage:  python -m src.stuff
Output: outputs/tables/stuff_by_pitch.csv
"""
from __future__ import annotations

import re
import sys
import unicodedata

import numpy as np
import pandas as pd

from src.config import KC, MIN_PITCHES_PER_TYPE, OUT_TABLES, PITCHES_PARQUET

PLATE_FRONT_Y = 17 / 12  # ft
START_Y = 50.0           # ft, where Statcast's 9-parameter fit starts

PITCH_GROUPS = {
    "FF": "FB", "SI": "FB", "FC": "FB",
    "SL": "BRK", "ST": "BRK", "CU": "BRK", "KC": "BRK", "SV": "BRK", "CS": "BRK",
    "CH": "OFF", "FS": "OFF", "FO": "OFF", "SC": "OFF",
}

# Not real pitch types for this analysis: eephus, pitchout, generic "fastball"
# (position players pitching), unknown, automatic ball, intentional ball.
EXCLUDE_PITCH_TYPES = {"EP", "PO", "FA", "UN", "AB", "IN"}

# Output metric -> source column after add_pitch_physics.
METRICS = {
    "velo": "release_speed", "ivb": "ivb", "hb": "hb", "arm_angle": "arm_angle",
    "release_height": "release_pos_z", "release_side": "release_pos_x",
    "extension": "release_extension", "vaa": "vaa", "livaa": "livaa",
}
PCTILE_METRICS = ["velo", "velo_max", "ivb", "hb", "arm_angle", "release_height",
                  "release_side", "extension", "vaa", "livaa", "stuff_plus"]

# FanGraphs pitch codes in Stuff+ columns -> Statcast pitch types.
FG_PITCH_MAP = {"FA": ["FF"], "SI": ["SI"], "FC": ["FC"], "SL": ["SL", "ST"],
                "CU": ["CU", "KC"], "KC": ["KC"], "CH": ["CH"], "FS": ["FS"],
                "FO": ["FO"], "SC": ["SC"], "ST": ["ST"], "SV": ["SV"]}


# ---------------------------------------------------------------- physics

def vaa(vy0, vz0, ay, az):
    """Vertical approach angle (degrees) at the front of home plate."""
    vy0, vz0, ay, az = (np.asarray(x, dtype=float) for x in (vy0, vz0, ay, az))
    vy_f = -np.sqrt(vy0 ** 2 - 2 * ay * (START_Y - PLATE_FRONT_Y))
    t = (vy_f - vy0) / ay
    vz_f = vz0 + az * t
    return -np.degrees(np.arctan(vz_f / vy_f))


def add_pitch_physics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ivb"] = df["pfx_z"] * 12
    df["hb"] = df["pfx_x"] * 12
    df["vaa"] = vaa(df["vy0"], df["vz0"], df["ay"], df["az"])
    df["pitch_group"] = df["pitch_type"].map(PITCH_GROUPS)
    return df


def livaa_fit(league: pd.DataFrame) -> pd.DataFrame:
    """Per pitch group: slope of VAA on plate_z and league mean plate_z."""
    rows = []
    for grp, g in league.dropna(subset=["vaa", "plate_z", "pitch_group"]).groupby("pitch_group"):
        slope, _ = np.polyfit(g["plate_z"], g["vaa"], 1)
        rows.append({"pitch_group": grp, "slope": slope, "mean_plate_z": g["plate_z"].mean(),
                     "n_fit": len(g)})
    return pd.DataFrame(rows)


def add_livaa(df: pd.DataFrame, fit: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(fit[["pitch_group", "slope", "mean_plate_z"]], on="pitch_group", how="left")
    df["livaa"] = df["vaa"] - df["slope"] * (df["plate_z"] - df["mean_plate_z"])
    return df.drop(columns=["slope", "mean_plate_z"])


# ---------------------------------------------------------------- tables

def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Per pitcher x pitch type. df = relief pitches with physics + livaa."""
    df = df[df["pitch_type"].notna() & ~df["pitch_type"].isin(EXCLUDE_PITCH_TYPES)]
    agg = {f"{m}": (c, "mean") for m, c in METRICS.items()}
    agg["velo_max"] = ("release_speed", "max")
    agg["n_pitches"] = ("release_speed", "size")
    agg["name"] = ("player_name", "first")
    agg["throws"] = ("p_throws", "first")
    out = df.groupby(["pitcher", "pitch_type"]).agg(**agg).reset_index()
    total = out.groupby("pitcher")["n_pitches"].transform("sum")
    out["usage_pct"] = (100 * out["n_pitches"] / total).round(1)
    out["pitch_group"] = out["pitch_type"].map(PITCH_GROUPS)
    out["sample_flag"] = np.where(out["n_pitches"] >= MIN_PITCHES_PER_TYPE, "",
                                  "insufficient sample")
    return out


def add_percentiles(tab: pd.DataFrame, qualified_ids) -> pd.DataFrame:
    """Percentile of each metric vs qualified relievers, same pitch type and hand."""
    tab = tab.copy()
    ok = tab["sample_flag"].eq("")
    ref = tab[ok & tab["pitcher"].isin(set(qualified_ids))]
    for m in PCTILE_METRICS:
        if m not in tab.columns:
            continue
        col = f"{m}_pctile"
        tab[col] = np.nan
        for (pt, hand), g in tab[ok].groupby(["pitch_type", "throws"]):
            pool = ref.loc[(ref["pitch_type"] == pt) & (ref["throws"] == hand), m].dropna().to_numpy()
            if len(pool) == 0:
                continue
            pool = np.sort(pool.astype(float))
            vals = g[m].to_numpy(dtype=float)
            # share of the pool at or below the value (mid-rank for ties), 0-100
            lo = np.searchsorted(pool, vals, side="left")
            hi = np.searchsorted(pool, vals, side="right")
            pct = 100 * (lo + hi) / 2 / len(pool)
            tab.loc[g.index, col] = np.where(np.isnan(vals), np.nan, pct.round(1))
    return tab


# ---------------------------------------------------------------- Stuff+

def name_key(name: str) -> str:
    """'Lange, Alex' or 'Alex Lange' -> 'alexlange' (accents, suffixes, punctuation dropped)."""
    if not isinstance(name, str):
        return ""
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        name = f"{first} {last}"
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", name.lower())
    return re.sub(r"[^a-z]", "", name)


def stuff_plus_long(fg: pd.DataFrame) -> pd.DataFrame:
    """FanGraphs player table -> one row per (id or name) x Statcast pitch type."""
    id_col = next((c for c in ("MLBAMID", "xMLBAMID", "mlbamid") if c in fg.columns), None)
    pat = re.compile(r"^(?:Stf\+|Stuff\+)\s*(?:_|\s)?\(?([A-Z]{2})\)?$")
    rows = []
    for col in fg.columns:
        m = pat.match(str(col).strip())
        if not m or m.group(1) not in FG_PITCH_MAP:
            continue
        for pt in FG_PITCH_MAP[m.group(1)]:
            part = pd.DataFrame({"pitch_type": pt, "stuff_plus": pd.to_numeric(fg[col], errors="coerce"),
                                 "fg_code": m.group(1)})
            part["name_key"] = fg["Name"].map(name_key) if "Name" in fg.columns else ""
            part["pitcher"] = pd.to_numeric(fg[id_col], errors="coerce") if id_col else np.nan
            rows.append(part)
    if not rows:
        return pd.DataFrame(columns=["pitcher", "name_key", "pitch_type", "stuff_plus", "fg_code"])
    out = pd.concat(rows, ignore_index=True).dropna(subset=["stuff_plus"])
    # An exact FanGraphs code (e.g. KC) beats a mapped one (CU -> KC).
    out["exact"] = out["fg_code"].eq(out["pitch_type"]) | (out["fg_code"].eq("FA") & out["pitch_type"].eq("FF"))
    key = "pitcher" if id_col else "name_key"
    out = out.sort_values("exact", ascending=False).drop_duplicates([key, "pitch_type"])
    return out.drop(columns=["exact"])


def overall_stuff_plus(fg: pd.DataFrame) -> pd.DataFrame:
    col = next((c for c in fg.columns if str(c).strip() in ("Stuff+", "Stf+")), None)
    if col is None or "Name" not in fg.columns:
        return pd.DataFrame(columns=["name_key", "stuff_plus_overall"])
    return pd.DataFrame({"name_key": fg["Name"].map(name_key),
                         "stuff_plus_overall": pd.to_numeric(fg[col], errors="coerce")}
                        ).drop_duplicates("name_key")


def join_stuff_plus(tab: pd.DataFrame, fg: pd.DataFrame | None) -> pd.DataFrame:
    tab = tab.copy()
    if fg is None or fg.empty:
        tab["stuff_plus"] = np.nan
        tab["stuff_plus_overall"] = np.nan
        return tab
    tab["name_key"] = tab["name"].map(name_key)
    long = stuff_plus_long(fg)
    if long["pitcher"].notna().any():
        tab = tab.merge(long[["pitcher", "pitch_type", "stuff_plus"]], on=["pitcher", "pitch_type"], how="left")
    else:
        tab = tab.merge(long[["name_key", "pitch_type", "stuff_plus"]], on=["name_key", "pitch_type"], how="left")
    tab = tab.merge(overall_stuff_plus(fg), on="name_key", how="left")
    return tab.drop(columns=["name_key"])


# ---------------------------------------------------------------- main

COLUMN_ORDER = ["pitcher", "name", "group", "throws", "pitch_type", "pitch_group", "n_pitches",
                "usage_pct", "sample_flag", "velo", "velo_max", "ivb", "hb", "arm_angle",
                "release_height", "release_side", "extension", "vaa", "livaa", "stuff_plus",
                "stuff_plus_overall"]


def build(pitches: pd.DataFrame, qualified_ids, kc_ids, fg: pd.DataFrame | None) -> pd.DataFrame:
    rel = add_pitch_physics(pitches[pitches["is_relief"]])
    fit = livaa_fit(rel[rel["pitcher"].isin(set(qualified_ids))])
    rel = add_livaa(rel, fit)
    tab = join_stuff_plus(summarize(rel), fg)
    tab = add_percentiles(tab, qualified_ids)
    tab["group"] = np.where(tab["pitcher"].isin(set(kc_ids)), "KC reliever", "MLB reliever")
    rounded = {c: 2 for c in ("velo", "velo_max", "ivb", "hb", "arm_angle", "release_height",
                              "release_side", "extension", "vaa", "livaa")}
    tab = tab.round(rounded)
    cols = COLUMN_ORDER + [c for c in tab.columns if c.endswith("_pctile")]
    return tab[[c for c in cols if c in tab.columns]].sort_values(
        ["group", "name", "n_pitches"], ascending=[True, True, False], ignore_index=True), fit


def main() -> int:
    from src.fangraphs import load_player_relievers
    pitches = pd.read_parquet(PITCHES_PARQUET)
    league = pd.read_csv(OUT_TABLES / "league_relievers_2026.csv")
    kc = pd.read_csv(OUT_TABLES / "kc_relievers_2026.csv")
    try:
        fg = load_player_relievers(offline=True)
    except FileNotFoundError as e:
        print(f"Stuff+ skipped: {e}")
        fg = None
    # KC pitches only count for KC relievers' KC appearances.
    kc_ids = set(kc["pitcher"])
    pitches = pitches[~pitches["pitcher"].isin(kc_ids) | pitches["pitching_team"].eq(KC)]
    tab, fit = build(pitches, league.loc[league["qualified"], "pitcher"], kc_ids, fg)
    tab.to_csv(OUT_TABLES / "stuff_by_pitch.csv", index=False)
    print("LiVAA fit (VAA on plate_z):")
    print(fit.round(3).to_string(index=False))
    print(f"Stuff+ matched on {tab['stuff_plus'].notna().mean():.0%} of rows")
    show = tab[(tab["group"] == "KC reliever") & tab["sample_flag"].eq("")]
    print(show[["name", "pitch_type", "n_pitches", "usage_pct", "velo", "ivb", "hb", "vaa",
                "livaa", "stuff_plus", "velo_pctile", "ivb_pctile", "vaa_pctile"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
