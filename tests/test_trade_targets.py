"""Unit tests for Step 7b trade-target rules. Hand-built frames check the rules only."""
import pandas as pd

from src.trade_targets import build, current_team, pick, shortlist


def pool(rows):
    base = dict(qualified=True, kc_own_fa=False, quadrant="Keep", age=27, primary_fb_pctile=50,
                execution_score=60, stuff_score=60, kill_pct_good=50, kill_pct=40.0, throws="R",
                team="SEA", relief_ip=50.0, control_through=float("nan"), status=float("nan"),
                primary_fb="FF", best_secondary="SL")
    return pd.DataFrame([{**base, **r} for r in rows])


def test_current_team_is_last_club():
    assert current_team("CWS/PHI") == "PHI"
    assert current_team("SEA") == "SEA"
    assert current_team(None) == ""


def test_pick_prefers_young_keeps_then_relaxes():
    rows = [dict(name=f"Y{i}", kill_pct_good=60 + i) for i in range(5)]
    p = pool(rows + [dict(name="Old", kill_pct_good=99, age=34)])
    assert "Old" not in pick(p, "execution", "kill_pct")["name"].tolist()
    p2 = pool(rows[:4] + [dict(name="Old", kill_pct_good=99, age=34)])
    assert pick(p2, "execution", "kill_pct")["name"].iloc[0] == "Old"


def test_pick_skips_unqualified_and_non_keep_when_enough():
    rows = [dict(name=f"K{i}", kill_pct_good=50 + i) for i in range(5)]
    p = pool(rows + [dict(name="Unq", kill_pct_good=99, qualified=False),
                     dict(name="Fix", kill_pct_good=98, quadrant="Execution fix")])
    names = pick(p, "execution", "kill_pct")["name"].tolist()
    assert "Unq" not in names and "Fix" not in names and names[0] == "K4"


def test_build_and_shortlist_dedupe():
    leak = pd.DataFrame([
        dict(reliever="Rep, A", qualified=True, quadrant="Replace candidate", primary_leak="x",
             leak_area="execution", leak_metric="kill_pct"),
        dict(reliever="Own, B", qualified=True, quadrant="Keep", primary_leak="x",
             leak_area="execution", leak_metric="kill_pct"),
        dict(reliever="Fix, C", qualified=True, quadrant="Execution fix", primary_leak="x",
             leak_area="execution", leak_metric="kill_pct"),
    ])
    p = pool([dict(name=f"T{i}", kill_pct_good=50 + i) for i in range(6)])
    t = build(leak, p, kc_fa_names=["B Own"])
    assert set(t["kc_reliever"]) == {"Rep, A", "Own, B"}
    assert (t["control_through"] == "?").all()
    s = shortlist(t)
    assert len(s) == 5 and s["n_leaks"].eq(2).all() and s.iloc[0]["target"] == "T5"
