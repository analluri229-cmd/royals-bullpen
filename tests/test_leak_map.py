"""Unit tests for Step 6 leak map. Tiny hand-built frames check the rules only."""
import numpy as np
import pandas as pd
import pytest

from src.leak_map import (execution_scores, fixable, ordinal, quadrant, rerank, sequencing_triage,
                          stuff_scores)


def stuff_rows(pid, pitches):
    """pitches: list of (pitch_type, usage_pct, stuff_plus_pctile, velo_pctile)."""
    return [dict(pitcher=pid, pitch_type=pt, usage_pct=u, stuff_plus_pctile=sp, velo_pctile=vp,
                 sample_flag="") for pt, u, sp, vp in pitches]


def test_stuff_score_weights_fb_best_secondary_rest():
    df = pd.DataFrame(stuff_rows(1, [("FF", 50, 80, 50), ("SL", 30, 40, 50), ("CH", 20, 60, 50)]))
    r = stuff_scores(df).iloc[0]
    assert r["primary_fb"] == "FF" and r["best_secondary"] == "CH"   # best, not most used
    assert r["stuff_score"] == pytest.approx(0.5 * 80 + 0.3 * 60 + 0.2 * 40)


def test_stuff_score_renormalizes_and_falls_back_to_velo():
    df = pd.DataFrame(stuff_rows(2, [("SI", 70, np.nan, 90), ("SL", 30, 30, 50)]))
    r = stuff_scores(df).iloc[0]
    # SI uses velo pctile 90; no "rest" -> weights 0.5/0.3 renormalized
    assert r["stuff_score"] == pytest.approx((0.5 * 90 + 0.3 * 30) / 0.8, abs=0.05)


def test_stuff_score_ignores_insufficient_sample_pitches():
    rows = stuff_rows(3, [("FF", 90, 50, 50), ("CU", 10, 99, 99)])
    rows[1]["sample_flag"] = "insufficient sample"
    assert stuff_scores(pd.DataFrame(rows)).iloc[0]["stuff_score"] == 50


def test_execution_score_inverts_bb():
    e = pd.DataFrame([dict(pitcher=1, sample_flag="", zone_pct_pctile=60, f_strike_pct_pctile=60,
                           three_ps_pct_pctile=60, kill_pct_pctile=60, bb_pct_pctile=90,
                           chase_pct_pctile=60)])
    out = execution_scores(e).iloc[0]
    assert out["bb_pct_good"] == 10
    assert out["execution_score"] == pytest.approx((60 * 5 + 10) / 6, abs=0.05)


@pytest.mark.parametrize("s,e,q", [(70, 70, "Keep"), (30, 70, "Stuff fix"), (70, 30, "Execution fix"),
                                   (30, 30, "Replace candidate"), (50, 50, "Keep"),
                                   (np.nan, 60, "Insufficient sample")])
def test_quadrant(s, e, q):
    assert quadrant(s, e) == q


def test_rerank_against_reference_only():
    v = pd.Series([10.0, 20.0, 30.0, 40.0, 99.0])
    ref = pd.Series([True, True, True, True, False])
    out = rerank(v, ref)
    assert out.tolist() == pytest.approx([12.5, 37.5, 62.5, 87.5, 100.0])


def test_fixable_rules():
    assert fixable("Keep", 36) == "Y"
    assert fixable("Execution fix", 28) == "Y"
    assert fixable("Execution fix", 34) == "?"
    assert fixable("Execution fix", 34, velo_drop=1.5) == "N"
    assert fixable("Replace candidate", 27) == "?"
    assert fixable("Replace candidate", 35) == "N"
    assert fixable("Stuff fix", 29, velo_drop=1.2) == "?"


def test_sequencing_triage_labels():
    seq = pd.DataFrame([
        dict(pitcher_id=1, pattern="tunneling", usage_pctile=20, lift_pctile=80, n_pitches=100, sample_flag=""),
        dict(pitcher_id=1, pattern="tunneling", usage_pctile=20, lift_pctile=60, n_pitches=100, sample_flag=""),
        dict(pitcher_id=1, pattern="delivery", usage_pctile=80, lift_pctile=20, n_pitches=100, sample_flag=""),
        dict(pitcher_id=2, pattern="delivery", usage_pctile=10, lift_pctile=10, n_pitches=100, sample_flag=""),
        dict(pitcher_id=3, pattern="delivery", usage_pctile=90, lift_pctile=90, n_pitches=100, sample_flag=""),
    ])
    t = sequencing_triage(seq).set_index(["pitcher_id", "pattern"])["triage"]
    assert t[(1, "tunneling")].startswith("effective but underused")   # mean of 80 and 60
    assert t[(1, "delivery")].startswith("used often, not working")
    assert t[(2, "delivery")] == "coaching target"
    assert t[(3, "delivery")] == "strength"


def test_ordinal():
    assert [ordinal(x) for x in (1, 2, 3, 4, 11, 12, 13, 21, 22.4)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]
