"""Unit tests for the pitch plinko (count tree) and pitch-mix-by-count tables."""
import pandas as pd
import pytest

from src.pitch_mix import mix_by_count
from src.plinko import plinko_tables, step, summary


@pytest.mark.parametrize("desc,b,s,want", [
    ("ball", 0, 0, "ball"), ("ball", 3, 1, "BB"), ("called_strike", 1, 1, "strike"),
    ("swinging_strike", 2, 2, "K"), ("foul", 0, 1, "strike"), ("foul", 1, 2, "foul_stay"),
    ("foul_bunt", 0, 2, "K"), ("hit_into_play", 2, 1, "in_play"), ("hit_by_pitch", 0, 0, "HBP"),
    ("blocked_ball", 3, 2, "BB"), ("foul_tip", 0, 2, "K"), ("weird", 0, 0, None)])
def test_step(desc, b, s, want):
    assert step(desc, b, s) == want


def _pa(ab, seq):
    """seq = list of (balls, strikes, description) for one PA by pitcher 1."""
    return [dict(pitcher=1, game_pk=1, at_bat_number=ab, balls=b, strikes=s, description=d) for b, s, d in seq]


def test_plinko_tables_reach_and_outcomes():
    rows = (_pa(1, [(0, 0, "called_strike"), (0, 1, "swinging_strike"), (0, 2, "swinging_strike")])  # K
            + _pa(2, [(0, 0, "ball"), (1, 0, "ball"), (2, 0, "ball"), (3, 0, "ball")])  # BB
            + _pa(3, [(0, 0, "hit_into_play")])
            + _pa(4, [(0, 0, "ball"), (1, 0, "called_strike"), (1, 1, "foul"), (1, 2, "foul"),
                      (1, 2, "hit_into_play")]))
    steps, reach = plinko_tables(pd.DataFrame(rows))
    r = reach.set_index("count")["reach_pct"]
    assert r["0-0"] == 100.0 and r["0-1"] == 25.0 and r["1-0"] == 50.0 and r["3-x"] == 25.0
    # the two-strike foul is counted once as a stay; PA 4 reaches 1-2 only once
    assert reach.set_index("count").loc["1-2", "pa_reached"] == 1
    sm = summary(steps, reach, 1)
    assert sm["pa"] == 4 and sm["k_pct"] == 25.0 and sm["bb_pct"] == 25.0 and sm["in_play_pct"] == 50.0


def test_mix_by_count_shares_and_relief_filter():
    p = pd.DataFrame([dict(pitcher=1, stand="R", balls=0, strikes=0, pitch_type=t, is_relief=rel)
                      for t, rel in [("FF", True), ("FF", True), ("SL", True), ("SL", False), ("PO", True)]])
    m = mix_by_count(p)
    row = m[(m["stand"] == "All") & (m["count"] == "0-0")].set_index("pitch_type")
    assert row.loc["FF", "usage_pct"] == pytest.approx(66.7) and row.loc["SL", "n"] == 1
    assert "PO" not in set(m["pitch_type"])
    assert set(m["count"]) == {"0-0", "All"} and set(m["stand"]) == {"R", "All"}
