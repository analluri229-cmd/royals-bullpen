"""Step 7: replacement targets from the 2026-27 free-agent reliever list.

Input: data/manual/fa_relievers_2026.csv (name, throws, age, war_mlbtr, option),
typed in from MLB Trade Rumors' free-agent list. Each free agent is matched by
name to the Step 4-6 tables (2026 relief work only).

For each KC reliever who is a Replace candidate, or a KC free agent (re-sign or
replace), list up to 3 free agents who are strong in that reliever's exact leak:
  execution leak  -> ranked by the leak metric's percentile (BB% inverted)
  stuff leak      -> ranked by stuff_score, then primary-fastball percentile
The pool is qualified free agents in the Keep quadrant (above average on both),
age 35 or under; if fewer than 3 qualify the age limit is dropped, then the
quadrant limit. KC's own free agents are never targets for each other.

Usage:  python -m src.targets
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.config import DATA_MANUAL, KC, OUT_TABLES
from src.leak_map import EXEC_LABELS, execution_scores, ordinal, stuff_scores
from src.stuff import name_key

N_TARGETS = 3
MAX_AGE = 35


def score_free_agents(fa, scores, exe, stuff, kc_names=()):
    """One row per free agent with 2026 scores, metric percentiles and a match flag."""
    fa = fa.copy()
    fa["name_key"] = fa["name"].map(name_key)
    es = execution_scores(exe)
    good = es[["pitcher"] + [f"{m}_good" for m in EXEC_LABELS] + list(EXEC_LABELS)]
    ss = stuff_scores(stuff)[["pitcher", "primary_fb", "primary_fb_pctile", "best_secondary",
                              "best_secondary_pctile"]]
    sc = scores.assign(name_key=scores["name"].map(name_key))
    sc = sc[~sc["group"].eq("KC reliever") | sc["name_key"].isin(set(map(name_key, kc_names)))]
    sc = sc.drop_duplicates("name_key")
    out = fa.merge(sc.drop(columns=["name"]), on="name_key", how="left")
    out = out.merge(good, on="pitcher", how="left").merge(ss, on="pitcher", how="left")
    out["matched"] = out["pitcher"].notna()
    out["qualified"] = out["qualified"].eq(True)
    out["kc_own_fa"] = out["name_key"].isin(set(map(name_key, kc_names)))
    return out.drop(columns="name_key")


def pick_targets(pool: pd.DataFrame, leak_area: str, leak_metric: str, n: int = N_TARGETS):
    p = pool[pool["qualified"] & ~pool["kc_own_fa"]].copy()
    if leak_area == "stuff":
        p["fit"] = p["stuff_score"]
        p = p.sort_values(["stuff_score", "primary_fb_pctile"], ascending=False)
    else:
        p["fit"] = p[f"{leak_metric}_good"]
        p = p.sort_values(["fit", "execution_score"], ascending=False)
    p = p[p["fit"].notna()]
    for mask in (p["quadrant"].eq("Keep") & (p["age"] <= MAX_AGE), p["quadrant"].eq("Keep"),
                 pd.Series(True, p.index)):
        if mask.sum() >= n:
            return p[mask].head(n)
    return p.head(n)


def build(leak, fa_scored):
    kc_fa = set(fa_scored.loc[fa_scored["kc_own_fa"], "name"].map(name_key))
    need = leak[leak["qualified"] & (leak["quadrant"].eq("Replace candidate")
                                     | leak["reliever"].map(name_key).isin(kc_fa))]
    rows = []
    for r in need.itertuples():
        why = "replace candidate" if r.quadrant == "Replace candidate" else "KC free agent: re-sign or replace"
        label = "Stuff score" if r.leak_area == "stuff" else EXEC_LABELS.get(r.leak_metric, r.leak_metric)
        for rank, t in enumerate(pick_targets(fa_scored, r.leak_area, r.leak_metric).itertuples(), 1):
            val = t.stuff_score if r.leak_area == "stuff" else getattr(t, r.leak_metric)
            rows.append(dict(kc_reliever=r.reliever, kc_quadrant=r.quadrant, reason=why,
                             leak=r.primary_leak, match_on=label, rank=rank, target=t.name, throws=t.throws,
                             age=t.age, option=t.option, war_mlbtr=t.war_mlbtr,
                             target_value=round(val, 1) if pd.notna(val) else np.nan,
                             target_pctile=t.fit, target_stuff_score=t.stuff_score,
                             target_execution_score=t.execution_score, target_quadrant=t.quadrant,
                             target_primary_fb=t.primary_fb, target_best_secondary=t.best_secondary,
                             note=f"{label} {ordinal(t.fit)} pct" + (f"; age {t.age}" if t.age >= 33 else "")))
    return pd.DataFrame(rows)


def run(leak, fa, scores, exe, stuff, kc_names):
    fa_scored = score_free_agents(fa, scores, exe, stuff, kc_names)
    targets = build(leak, fa_scored)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    fa_scored.to_csv(OUT_TABLES / "fa_relievers_scored.csv", index=False)
    targets.to_csv(OUT_TABLES / "targets.csv", index=False)
    pd.set_option("display.width", 250)
    print(f"{fa_scored['matched'].sum()} of {len(fa_scored)} free agents matched; "
          f"{fa_scored['qualified'].sum()} qualified")
    print(fa_scored[fa_scored["qualified"]]["quadrant"].value_counts().to_string())
    print(targets[["kc_reliever", "match_on", "rank", "target", "throws", "age", "target_pctile",
                   "target_stuff_score", "target_execution_score"]].to_string(index=False))
    return fa_scored, targets


def main() -> int:
    fa = pd.read_csv(DATA_MANUAL / "fa_relievers_2026.csv")
    kc = pd.read_csv(OUT_TABLES / "kc_relievers_2026.csv")
    run(pd.read_csv(OUT_TABLES / "leak_map.csv"), fa, pd.read_csv(OUT_TABLES / "scores_all_relievers.csv"),
        pd.read_csv(OUT_TABLES / "execution_by_reliever.csv"), pd.read_csv(OUT_TABLES / "stuff_by_pitch.csv"),
        kc["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
