"""Unit tests for Step 7 target matching. Hand-built frames check the rules only."""
import pandas as pd

from src.targets import build, pick_targets


def pool(rows):
    base = dict(qualified=True, kc_own_fa=False, quadrant="Keep", age=30, primary_fb_pctile=50,
                execution_score=60, stuff_score=60, kill_pct_good=50, kill_pct=40.0, throws="R",
                option="", war_mlbtr=1.0, primary_fb="FF", best_secondary="SL")
    return pd.DataFrame([{**base, **r} for r in rows])


def test_pick_ranks_by_leak_metric_and_skips_own_fa():
    p = pool([dict(name="A", kill_pct_good=90), dict(name="B", kill_pct_good=70),
              dict(name="C", kill_pct_good=95, kc_own_fa=True), dict(name="D", kill_pct_good=80)])
    assert pick_targets(p, "execution", "kill_pct")["name"].tolist() == ["A", "D", "B"]


def test_pick_prefers_keep_and_age_limit_then_relaxes():
    p = pool([dict(name="Old", kill_pct_good=99, age=38), dict(name="Low", kill_pct_good=98, quadrant="Stuff fix"),
              dict(name="A", kill_pct_good=60), dict(name="B", kill_pct_good=55), dict(name="C", kill_pct_good=52)])
    assert pick_targets(p, "execution", "kill_pct")["name"].tolist() == ["A", "B", "C"]
    # only 2 young Keeps -> drop the age limit, still Keep only
    p2 = p[p["name"] != "C"]
    assert pick_targets(p2, "execution", "kill_pct")["name"].tolist() == ["Old", "A", "B"]


def test_pick_stuff_leak_uses_stuff_score():
    p = pool([dict(name="A", stuff_score=70), dict(name="B", stuff_score=90), dict(name="C", stuff_score=80)])
    assert pick_targets(p, "stuff", "stuff_score")["name"].tolist() == ["B", "C", "A"]


def test_build_only_replace_candidates_and_kc_free_agents():
    leak = pd.DataFrame([
        dict(reliever="Rep, A", qualified=True, quadrant="Replace candidate", primary_leak="x",
             leak_area="execution", leak_metric="kill_pct"),
        dict(reliever="Fix, B", qualified=True, quadrant="Execution fix", primary_leak="x",
             leak_area="execution", leak_metric="kill_pct"),
        dict(reliever="Own, C", qualified=True, quadrant="Keep", primary_leak="x",
             leak_area="execution", leak_metric="kill_pct"),
    ])
    fa = pool([dict(name="T1", kill_pct_good=90), dict(name="T2", kill_pct_good=80),
               dict(name="T3", kill_pct_good=70), dict(name="C Own", kc_own_fa=True)])
    out = build(leak, fa)
    assert set(out["kc_reliever"]) == {"Rep, A", "Own, C"}
    assert out[out["kc_reliever"] == "Rep, A"]["target"].tolist() == ["T1", "T2", "T3"]
