"""Step 7b: trade targets, relievers on other MLB teams who fit KC's leaks.

Same matching rules as src/targets.py (free agents), applied to every qualified
MLB reliever who is not a Royal and not on the 2026-27 free-agent list:
  execution leak  -> ranked by the leak metric's percentile (BB% inverted)
  stuff leak      -> ranked by stuff_score, then primary-fastball percentile
Pool: Keep quadrant (above average on Stuff and Execution), age 31 or under
(younger relievers usually carry more years of team control); the age limit is
dropped, then the quadrant limit, if fewer than N_TARGETS qualify.

Team control is not in Statcast. If data/manual/trade_control_2026.csv exists
(name, team, control_through, status, salary_2027_m; from Spotrac, Cot's or
FanGraphs RosterResource), it is joined in, and anyone whose control ends in
2026 is dropped. Without it, every shortlisted name is written to
data/manual/trade_control_2026_template.csv to be filled in, and control shows "?".

Outputs: outputs/tables/trade_targets.csv (per KC leak) and
         outputs/tables/trade_shortlist.csv (one row per target, deduped).

Usage:  python -m src.trade_targets
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from src.config import DATA_MANUAL, OUT_TABLES, SEASON
from src.leak_map import EXEC_LABELS, ordinal
from src.stuff import name_key
from src.targets import score_free_agents

N_TARGETS = 5
MAX_AGE = 31
CONTROL_FILE = DATA_MANUAL / "trade_control_2026.csv"
TEMPLATE_FILE = DATA_MANUAL / "trade_control_2026_template.csv"
CONTROL_COLS = ["control_through", "status", "salary_2027_m"]


def current_team(teams: str) -> str:
    """'CWS/PHI' -> 'PHI' (the last club he pitched for in 2026)."""
    return teams.split("/")[-1].strip() if isinstance(teams, str) and teams else ""


def trade_pool(league, scores, exe, stuff, fa_names, ages, control=None):
    """Scored, non-KC, non-free-agent MLB relievers with team, age and control."""
    lg = league[["pitcher", "name", "throws", "teams", "relief_ip"]].copy()
    lg["team"] = lg["teams"].map(current_team)
    fa_keys = set(map(name_key, fa_names))
    lg = lg[~lg["name"].map(name_key).isin(fa_keys)]
    lg = lg[scores.set_index("pitcher").reindex(lg["pitcher"])["group"].eq("MLB reliever").to_numpy()]
    lg = lg.merge(ages, on="pitcher", how="left")
    pool = score_free_agents(lg.drop(columns=["pitcher"]), scores, exe, stuff)
    pool["kc_own_fa"] = False  # nobody here is a KC free agent; keeps pick rules shared
    if control is not None and len(control):
        c = control.assign(name_key=control["name"].map(name_key)).drop_duplicates("name_key")
        pool = (pool.assign(name_key=pool["name"].map(name_key))
                .merge(c[["name_key"] + [k for k in CONTROL_COLS if k in c]], on="name_key", how="left")
                .drop(columns="name_key"))
        ends_now = pd.to_numeric(pool["control_through"], errors="coerce").le(SEASON)
        pool = pool[~ends_now]
    for k in CONTROL_COLS:
        if k not in pool:
            pool[k] = np.nan
    return pool


def pick(pool: pd.DataFrame, leak_area: str, leak_metric: str, n: int = N_TARGETS):
    p = pool[pool["qualified"]].copy()
    if leak_area == "stuff":
        p["fit"] = p["stuff_score"]
        p = p.sort_values(["stuff_score", "primary_fb_pctile"], ascending=False)
    else:
        p["fit"] = p[f"{leak_metric}_good"]
        p = p.sort_values(["fit", "execution_score"], ascending=False)
    p = p[p["fit"].notna()]
    keep = p["quadrant"].eq("Keep")
    young = p["age"].le(MAX_AGE)
    for mask in (keep & young, keep, pd.Series(True, p.index)):
        if mask.sum() >= n:
            return p[mask].head(n)
    return p.head(n)


def build(leak, pool, kc_fa_names=()):
    kc_fa = set(map(name_key, kc_fa_names))
    need = leak[leak["qualified"] & (leak["quadrant"].eq("Replace candidate")
                                     | leak["reliever"].map(name_key).isin(kc_fa))]
    rows = []
    for r in need.itertuples():
        why = "replace candidate" if r.quadrant == "Replace candidate" else "KC free agent: re-sign or replace"
        label = "Stuff score" if r.leak_area == "stuff" else EXEC_LABELS.get(r.leak_metric, r.leak_metric)
        for rank, t in enumerate(pick(pool, r.leak_area, r.leak_metric).itertuples(), 1):
            val = t.stuff_score if r.leak_area == "stuff" else getattr(t, r.leak_metric)
            ctl = t.control_through
            rows.append(dict(kc_reliever=r.reliever, kc_quadrant=r.quadrant, reason=why, leak=r.primary_leak,
                             match_on=label, rank=rank, target=t.name, team=t.team, throws=t.throws,
                             age=t.age, relief_ip=round(t.relief_ip, 1),
                             control_through=ctl if pd.notna(ctl) else "?",
                             status=t.status if pd.notna(t.status) else "?",
                             target_value=round(val, 1) if pd.notna(val) else np.nan, target_pctile=t.fit,
                             target_stuff_score=t.stuff_score, target_execution_score=t.execution_score,
                             target_quadrant=t.quadrant, target_primary_fb=t.primary_fb,
                             target_best_secondary=t.best_secondary,
                             note=f"{label} {ordinal(t.fit)} pct" + (f"; age {t.age:.0f}" if t.age >= 33 else "")))
    return pd.DataFrame(rows)


def shortlist(targets: pd.DataFrame) -> pd.DataFrame:
    """One row per target: which KC leaks he covers, best rank first."""
    if targets.empty:
        return targets
    g = targets.groupby("target", sort=False)
    out = g.agg(team=("team", "first"), throws=("throws", "first"), age=("age", "first"),
                relief_ip=("relief_ip", "first"), control_through=("control_through", "first"),
                status=("status", "first"), stuff_score=("target_stuff_score", "first"),
                execution_score=("target_execution_score", "first"),
                primary_fb=("target_primary_fb", "first"), best_secondary=("target_best_secondary", "first"),
                best_rank=("rank", "min"), n_leaks=("kc_reliever", "nunique"),
                covers=("kc_reliever", lambda s: "; ".join(dict.fromkeys(s))),
                match_on=("match_on", lambda s: "; ".join(dict.fromkeys(s)))).reset_index()
    return out.sort_values(["n_leaks", "best_rank", "execution_score"], ascending=[False, True, False])


def write_template(short: pd.DataFrame, path=TEMPLATE_FILE):
    t = short[["target", "team", "age"]].rename(columns={"target": "name"})
    for k in CONTROL_COLS:
        t[k] = ""
    t.to_csv(path, index=False)


def main() -> int:
    t = lambda f: pd.read_csv(OUT_TABLES / f)
    fa = pd.read_csv(DATA_MANUAL / "fa_relievers_2026.csv")
    control = pd.read_csv(CONTROL_FILE) if CONTROL_FILE.exists() else None
    pool = trade_pool(t("league_relievers_2026.csv"), t("scores_all_relievers.csv"),
                      t("execution_by_reliever.csv"), t("stuff_by_pitch.csv"), fa["name"],
                      t("pitcher_age_2026.csv"), control)
    kc_fa = t("fa_relievers_scored.csv").query("kc_own_fa")["name"]
    targets = build(t("leak_map.csv"), pool, kc_fa)
    short = shortlist(targets)
    targets.to_csv(OUT_TABLES / "trade_targets.csv", index=False)
    short.to_csv(OUT_TABLES / "trade_shortlist.csv", index=False)
    if control is None:
        write_template(short)
        print(f"No {CONTROL_FILE.name}; fill in {TEMPLATE_FILE.name} and save it as {CONTROL_FILE.name}")
    pd.set_option("display.width", 250)
    print(f"Trade pool: {pool['qualified'].sum()} qualified non-KC, non-FA relievers; "
          f"{pool[pool['qualified']]['quadrant'].eq('Keep').sum()} in Keep")
    print(short.drop(columns=["covers"]).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
