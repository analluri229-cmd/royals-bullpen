"""Step 6: leak map and fix-or-replace triage.

Inputs (all from earlier steps, in outputs/tables):
  stuff_by_pitch.csv          per pitch type, with percentiles vs same type and hand
  execution_by_reliever.csv   per reliever, raw percentiles (100 = highest value)
  sequencing_by_pitcher.csv   Step 5A patterns (How often / How well percentiles)
  pitcher_age_2026.csv        season age from Statcast age_pit
  data/manual/royals_contracts.csv  optional: name, contract_status, years_control

Scores (0-100, 50 = league-average qualified reliever):
  stuff_score      per-pitch Stuff percentile = FanGraphs Stuff+ percentile (same
                   pitch type and hand), falling back to the velocity percentile
                   when Stuff+ is missing. Weighted: primary fastball 50%, best
                   secondary 30%, the rest 20% (usage-weighted). Missing parts are
                   dropped and the weights renormalized.
  execution_score  mean percentile of Zone%, F-Strike%, 3PS%, Kill%, Chase% and
                   BB% (inverted, so 100 = fewest walks).
Both composites are then re-ranked as percentiles among qualified league relievers
(raw values kept as stuff_composite / execution_composite). Taking the *best*
secondary pushes the raw Stuff composite above 50 for most pitchers, so without
the re-rank the 50 cut line would not mean "league average".
Quadrants at 50/50: Keep, Stuff fix, Execution fix, Replace candidate.

Usage:  python -m src.leak_map
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.config import DATA_MANUAL, OUT_TABLES

CUT = 50.0
FB_TYPES = {"FF", "SI", "FC"}
WEIGHTS = {"fb": 0.5, "second": 0.3, "rest": 0.2}
EXEC_METRICS = ["zone_pct", "f_strike_pct", "three_ps_pct", "kill_pct", "bb_pct", "chase_pct"]
INVERTED = {"bb_pct"}
EXEC_LABELS = {"zone_pct": "Zone%", "f_strike_pct": "F-Strike%", "three_ps_pct": "3PS%",
               "kill_pct": "Kill%", "bb_pct": "BB%", "chase_pct": "Chase%"}
EXEC_FIX = {
    "zone_pct": "attack the zone: more fastballs and secondaries in the zone early",
    "f_strike_pct": "win pitch 1: a first-pitch strike plan (in-zone fastball or get-me-over breaker)",
    "three_ps_pct": "get to two strikes in three pitches: strikes early in the count",
    "kill_pct": "build a put-away plan with two strikes (best whiff pitch, located below the zone)",
    "bb_pct": "cut walks: fewer non-competitive pitches behind in the count",
    "chase_pct": "get chases: start secondaries in the zone and finish them off it",
}
AGE_FLAG = 33


def ordinal(x: float) -> str:
    n = int(round(x))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def rerank(values: pd.Series, ref_mask: pd.Series) -> pd.Series:
    """Percentile (0-100, mid-rank for ties) of each value within the reference rows."""
    pool = np.sort(values[ref_mask].dropna().to_numpy(float))
    v = values.to_numpy(float)
    if len(pool) == 0:
        return pd.Series(np.nan, values.index)
    lo, hi = np.searchsorted(pool, v, "left"), np.searchsorted(pool, v, "right")
    return pd.Series(np.where(np.isnan(v), np.nan, (100 * (lo + hi) / 2 / len(pool)).round(1)), values.index)


def pctile_good(row: pd.Series, metric: str) -> float:
    """Percentile where higher is always better."""
    v = row.get(f"{metric}_pctile", np.nan)
    return 100 - v if metric in INVERTED and pd.notna(v) else v


# ---------------------------------------------------------------- Stuff score

def pitch_stuff_pctile(stuff: pd.DataFrame) -> pd.Series:
    sp = stuff["stuff_plus_pctile"] if "stuff_plus_pctile" in stuff else pd.Series(np.nan, stuff.index)
    return sp.fillna(stuff["velo_pctile"])


def stuff_scores(stuff: pd.DataFrame) -> pd.DataFrame:
    """One row per pitcher: stuff_score plus the parts it came from."""
    s = stuff[stuff["sample_flag"].fillna("").eq("")].copy()
    s["pitch_pct"] = pitch_stuff_pctile(s)
    s = s[s["pitch_pct"].notna()]
    rows = []
    for pid, g in s.groupby("pitcher"):
        g = g.sort_values("usage_pct", ascending=False)
        fbs = g[g["pitch_type"].isin(FB_TYPES)]
        primary = fbs.iloc[0] if len(fbs) else g.iloc[0]
        others = g[g.index != primary.name]
        second = others.loc[others["pitch_pct"].idxmax()] if len(others) else None
        rest = others.drop(second.name) if second is not None else others
        parts = {"fb": primary["pitch_pct"],
                 "second": second["pitch_pct"] if second is not None else np.nan,
                 "rest": np.average(rest["pitch_pct"], weights=rest["usage_pct"]) if len(rest) else np.nan}
        w = {k: WEIGHTS[k] for k, v in parts.items() if pd.notna(v)}
        score = sum(parts[k] * w[k] for k in w) / sum(w.values())
        rows.append(dict(pitcher=pid, stuff_score=round(score, 1),
                         primary_fb=primary["pitch_type"], primary_fb_pctile=parts["fb"],
                         best_secondary=second["pitch_type"] if second is not None else "",
                         best_secondary_pctile=parts["second"], rest_pctile=round(parts["rest"], 1)
                         if pd.notna(parts["rest"]) else np.nan))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Execution score

def execution_scores(exe: pd.DataFrame) -> pd.DataFrame:
    e = exe[exe["sample_flag"].fillna("").eq("")].copy()
    good = pd.DataFrame({m: e.apply(pctile_good, axis=1, metric=m) for m in EXEC_METRICS})
    e["execution_score"] = good.mean(axis=1, skipna=True).round(1)
    for m in EXEC_METRICS:
        e[f"{m}_good"] = good[m]
    return e


def quadrant(stuff_score: float, execution_score: float) -> str:
    if pd.isna(stuff_score) or pd.isna(execution_score):
        return "Insufficient sample"
    hi_s, hi_e = stuff_score >= CUT, execution_score >= CUT
    if hi_s and hi_e:
        return "Keep"
    if hi_e:
        return "Stuff fix"
    if hi_s:
        return "Execution fix"
    return "Replace candidate"


# ---------------------------------------------------------------- leaks

def league_medians(exe: pd.DataFrame, qualified_ids) -> dict:
    ref = exe[exe["pitcher"].isin(set(qualified_ids)) & exe["sample_flag"].fillna("").eq("")]
    return {m: ref[m].median() for m in EXEC_METRICS}


def stuff_medians(stuff: pd.DataFrame, qualified_ids) -> pd.DataFrame:
    ref = stuff[stuff["pitcher"].isin(set(qualified_ids)) & stuff["sample_flag"].fillna("").eq("")]
    return ref.groupby(["pitch_type", "throws"])[["stuff_plus", "velo"]].median()


def worst_execution(row: pd.Series, med: dict) -> tuple[str, float, str]:
    vals = {m: row.get(f"{m}_good", np.nan) for m in EXEC_METRICS}
    vals = {m: v for m, v in vals.items() if pd.notna(v)}
    if not vals:
        return "", np.nan, ""
    m = min(vals, key=vals.get)
    text = (f"{EXEC_LABELS[m]} {row[m]:.1f} vs league {med[m]:.1f} "
            f"({ordinal(vals[m])} pct{', inverted' if m in INVERTED else ''})")
    return m, vals[m], text


def worst_pitch(stuff: pd.DataFrame, pid: int, smed: pd.DataFrame, min_usage: float = 10.0) -> str:
    g = stuff[(stuff["pitcher"] == pid) & stuff["sample_flag"].fillna("").eq("")].copy()
    g["pitch_pct"] = pitch_stuff_pctile(g)
    g = g[(g["usage_pct"] >= min_usage) & g["pitch_pct"].notna()]
    if g.empty:
        return ""
    r = g.loc[g["pitch_pct"].idxmin()]
    key = (r["pitch_type"], r["throws"])
    if pd.notna(r.get("stuff_plus")) and key in smed.index:
        base = f"{r['pitch_type']} Stuff+ {r['stuff_plus']:.0f} vs league {smed.loc[key, 'stuff_plus']:.0f}"
    else:
        base = f"{r['pitch_type']} velo {r['velo']:.1f} mph"
    detail = []
    if r["pitch_type"] == "FF":
        for m, lab in [("velo", "velo"), ("ivb", "IVB"), ("livaa", "LiVAA")]:
            p = r.get(f"{m}_pctile")
            if pd.notna(p) and p < 30:
                detail.append(f"{lab} {ordinal(p)} pct")
    extra = f"; {', '.join(detail)}" if detail else ""
    return f"{base} ({ordinal(r['pitch_pct'])} pct, {r['usage_pct']:.0f}% usage{extra})"


# ---------------------------------------------------------------- sequencing triage

def sequencing_triage(seq: pd.DataFrame) -> pd.DataFrame:
    """One row per pitcher x pattern with a triage label from How often vs How well.

    Tunneling has two outcome rows (whiff and chase); How well is their mean lift pctile.
    """
    s = seq.groupby(["pitcher_id", "pattern"], as_index=False).agg(
        often=("usage_pctile", "first"), well=("lift_pctile", "mean"), n=("n_pitches", "first"),
        flag=("sample_flag", "first"))

    def label(r):
        if pd.isna(r["often"]) or pd.isna(r["well"]):
            return "insufficient sample"
        if r["well"] >= CUT and r["often"] < CUT:
            return "effective but underused: use it more"
        if r["often"] >= CUT and r["well"] < CUT:
            return "used often, not working: cut back or fix the pitch it depends on"
        if r["often"] < CUT and r["well"] < CUT:
            return "coaching target"
        return "strength"
    s["triage"] = s.apply(label, axis=1)
    return s


PATTERN_PLAN = {
    ("delivery", "coaching target"): "tighten release: match the secondary's release point to the fastball's (video review)",
    ("delivery", "used often, not working: cut back or fix the pitch it depends on"):
        "release gap tips pitches: close the gap between fastball and secondary release",
    ("delivery", "effective but underused: use it more"):
        "release is close on average but drifts pitch to pitch: tighten release consistency",
    ("tunneling", "coaching target"): "pair pitches that share a tunnel; redesign the secondary off the fastball's path",
    ("tunneling", "effective but underused: use it more"): "throw the tunneled pairs more often",
    ("tunneling", "used often, not working: cut back or fix the pitch it depends on"):
        "tunneled pairs aren't missing bats: sharpen the late break on the second pitch",
}


def seq_plan(tri: pd.DataFrame, pid: int) -> str:
    t = tri[(tri["pitcher_id"] == pid) & ~tri["triage"].isin(["strength", "insufficient sample"])]
    t = t.assign(gap=t[["often", "well"]].min(axis=1)).sort_values("gap")
    plans = [PATTERN_PLAN.get((r.pattern, r.triage), f"{r.pattern}: {r.triage}") for r in t.itertuples()]
    return "; ".join(plans[:2])


# ---------------------------------------------------------------- fixability

def fixable(quad: str, age: float, velo_drop: float | None = None) -> str:
    """Y / N / ? from quadrant, age and (if known) fastball velocity drop vs 2024-25."""
    old = pd.notna(age) and age >= AGE_FLAG
    dropped = velo_drop is not None and pd.notna(velo_drop) and velo_drop >= 1.0
    if quad == "Keep":
        return "Y"
    if quad == "Insufficient sample":
        return "?"
    if quad == "Replace candidate":
        return "N" if (old or dropped) else "?"
    if old and dropped:
        return "N"
    return "?" if (old or dropped) else "Y"


def action(quad: str, fix: str, leak_metric: str, plan: str) -> str:
    if quad == "Keep":
        return "Keep in high-leverage role" + (f"; refine: {plan}" if plan else "")
    if quad == "Stuff fix":
        return "Pitch design: new shape or new pitch for the weak offering" + (f"; {plan}" if plan else "")
    if quad == "Execution fix":
        base = EXEC_FIX.get(leak_metric, "execution plan")
        return base[0].upper() + base[1:] + (f"; {plan}" if plan else "")
    if quad == "Replace candidate":
        return ("Replace: acquire a target strong in this leak" if fix == "N"
                else "Replace candidate: low-cost development try, but line up a replacement")
    return "Small sample: reassess in spring"


def load_contracts() -> pd.DataFrame | None:
    p = DATA_MANUAL / "royals_contracts.csv"
    return pd.read_csv(p) if p.exists() else None


# ---------------------------------------------------------------- build

def build(stuff, exe, seq, ages, qualified_ids, kc_qualified_ids=None, contracts=None):
    ss = stuff_scores(stuff)
    es = execution_scores(exe)
    med, smed = league_medians(exe, qualified_ids), stuff_medians(stuff, qualified_ids)
    tri = sequencing_triage(seq)
    tab = es[["pitcher", "name", "group", "throws", "pa"] + EXEC_METRICS
             + [f"{m}_good" for m in EXEC_METRICS] + ["execution_score"]].merge(ss, on="pitcher", how="left")
    tab = tab.merge(ages.rename(columns={"age": "age"}), on="pitcher", how="left")
    ref = tab["pitcher"].isin(set(qualified_ids))
    for c in ["stuff", "execution"]:
        tab[f"{c}_composite"] = tab[f"{c}_score"]
        tab[f"{c}_score"] = rerank(tab[f"{c}_composite"], ref)
    tab["quadrant"] = [quadrant(a, b) for a, b in zip(tab["stuff_score"], tab["execution_score"])]
    tab["qualified"] = ref
    if kc_qualified_ids is not None:  # KC rows use KC-only relief totals (Step 1)
        kc_rows = tab["group"].eq("KC reliever")
        tab.loc[kc_rows, "qualified"] = tab.loc[kc_rows, "pitcher"].isin(set(kc_qualified_ids))

    kc = tab["group"].eq("KC reliever")
    out = []
    for r in tab[kc].itertuples():
        row = tab.loc[r.Index]
        em, ev, etxt = worst_execution(row, med)
        ptxt = worst_pitch(stuff, r.pitcher, smed)
        if r.quadrant == "Stuff fix" or (r.quadrant == "Replace candidate" and r.stuff_score < r.execution_score):
            primary = f"Stuff: {ptxt}" if ptxt else "Stuff"
            leak_area, leak_metric = "stuff", "stuff_score"
        elif r.quadrant in ("Execution fix", "Replace candidate"):
            primary = f"Execution: {etxt}"
            leak_area, leak_metric = "execution", em
        else:
            primary = f"Smallest gap: {etxt}" if etxt else ""
            leak_area, leak_metric = "execution", em
        plan = seq_plan(tri, r.pitcher)
        flags = []
        if pd.notna(r.age) and r.age >= AGE_FLAG:
            flags.append(f"age {int(r.age)}")
        flags.append("velo trend vs 2024-25 not checked")
        quad = r.quadrant if r.qualified else "Insufficient sample"
        fix = fixable(quad, r.age)
        out.append(dict(pitcher=r.pitcher, reliever=r.name, qualified=r.qualified, age=r.age,
                        stuff_score=r.stuff_score, execution_score=r.execution_score, quadrant=quad,
                        quadrant_if_full_sample=r.quadrant, leak_area=leak_area, leak_metric=leak_metric, stuff_composite=r.stuff_composite,
                        execution_composite=r.execution_composite,
                        primary_leak=primary, weakest_pitch=ptxt, weakest_execution=etxt,
                        sequencing_plan=plan, fixable=fix, fixability_flags="; ".join(flags),
                        recommended_action=action(quad, fix, em, plan)))
    leak = pd.DataFrame(out)
    if contracts is not None and len(leak):
        from src.stuff import name_key
        c = contracts.assign(_k=contracts["name"].map(name_key)).drop(columns="name")
        leak = leak.assign(_k=leak["reliever"].map(name_key)).merge(c, on="_k", how="left").drop(columns="_k")
    leak = leak.sort_values(["qualified", "stuff_score"], ascending=[False, False])
    league = tab[["pitcher", "name", "group", "qualified", "stuff_score", "execution_score", "quadrant",
                  "stuff_composite", "execution_composite"]]
    return leak, league, tri


def ages_from_pitches(pitches: pd.DataFrame) -> pd.DataFrame:
    return pitches.groupby("pitcher", as_index=False)["age_pit"].max().rename(columns={"age_pit": "age"})


def run(stuff, exe, seq, ages, qualified_ids, kc_qualified_ids=None, contracts=None):
    leak, league, tri = build(stuff, exe, seq, ages, qualified_ids, kc_qualified_ids, contracts)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    cols = ["reliever", "stuff_score", "execution_score", "quadrant", "primary_leak", "fixable",
            "recommended_action"]
    leak[cols + [c for c in leak.columns if c not in cols]].to_csv(OUT_TABLES / "leak_map.csv", index=False)
    league.to_csv(OUT_TABLES / "scores_all_relievers.csv", index=False)
    tri.to_csv(OUT_TABLES / "sequencing_triage.csv", index=False)
    pd.set_option("display.width", 250, "display.max_colwidth", 90)
    print(leak[leak["qualified"]][["reliever", "age", "stuff_score", "execution_score", "quadrant",
                                   "fixable", "primary_leak"]].to_string(index=False))
    q = league[league["qualified"]]
    print("\nLeague qualified relievers by quadrant:\n", q["quadrant"].value_counts().to_string())
    return leak, league, tri


def main() -> int:
    stuff = pd.read_csv(OUT_TABLES / "stuff_by_pitch.csv")
    exe = pd.read_csv(OUT_TABLES / "execution_by_reliever.csv")
    seq = pd.read_csv(OUT_TABLES / "sequencing_by_pitcher.csv")
    age_csv = OUT_TABLES / "pitcher_age_2026.csv"
    if age_csv.exists():
        ages = pd.read_csv(age_csv)
    else:
        from src.config import PITCHES_PARQUET
        ages = ages_from_pitches(pd.read_parquet(PITCHES_PARQUET, columns=["pitcher", "age_pit"]))
        ages.to_csv(age_csv, index=False)
    league = pd.read_csv(OUT_TABLES / "league_relievers_2026.csv")
    kc = pd.read_csv(OUT_TABLES / "kc_relievers_2026.csv")
    run(stuff, exe, seq, ages, league.loc[league["qualified"], "pitcher"],
        kc.loc[kc["qualified"], "pitcher"], load_contracts())
    return 0


if __name__ == "__main__":
    sys.exit(main())
