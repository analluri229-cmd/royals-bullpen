"""Unit tests for Step 7 prospect handling. Hand-built frames check the rules only."""
import pandas as pd

from src.prospects import build, bullpen_timing, fv_number


def test_bullpen_timing():
    assert bullpen_timing("SIRP", 2026) == "now"
    assert bullpen_timing("SP", 2026) == "convert"
    assert bullpen_timing("SIRP", 2028) == "later"
    assert bullpen_timing("SP", "?") == "unknown"


def test_fv_number():
    assert fv_number("40+") == 42.5 and fv_number("45") == 45.0 and fv_number(50) == 50.0


def test_build_keeps_pitchers_and_flags_data():
    pros = pd.DataFrame([
        dict(rank=1, name="Carter Jensen", age=22.8, highest_level="MLB", position="C", eta=2026, fv="50"),
        dict(rank=6, name="Luinder Avila", age=24.7, highest_level="MLB", position="SIRP", eta=2026, fv="45"),
        dict(rank=28, name="Eric Cerantola", age=26.0, highest_level="AAA", position="SIRP", eta=2026, fv="35+"),
        dict(rank=12, name="Ben Kudrna", age=23.2, highest_level="AAA", position="SP", eta=2026, fv="40+"),
    ])
    scores = pd.DataFrame([dict(name="Avila, Luinder", pitcher=1, qualified=True, stuff_score=80.0,
                                execution_score=4.0, quadrant="Execution fix")])
    stuff = pd.DataFrame([dict(name="Avila, Luinder", n_pitches=300), dict(name="Cerantola, Eric", n_pitches=40)])
    out = build(pros, scores, stuff).set_index("name")
    assert "Carter Jensen" not in out.index
    assert out.loc["Luinder Avila", "data"] == "MLB 2026 Statcast (scored)"
    assert out.loc["Eric Cerantola", "data"].startswith("MLB 2026 Statcast (small sample")
    assert out.loc["Ben Kudrna", "data"] == "no tracking data loaded"
    assert out.loc["Ben Kudrna", "timing"] == "convert"
    assert list(out.index) == ["Luinder Avila", "Eric Cerantola", "Ben Kudrna"]


def test_future_grade_and_fit():
    from src.prospects import future_grade, grade_fit
    assert future_grade("50/60") == 60 and pd.isna(future_grade(None))
    row = pd.Series(dict(slider="70/70", curveball=None, changeup=None, cutter="45/45", command="30/35", tops=98))
    assert grade_fit(row) == "bat-miss slider (70), velocity (tops 98)"
    row2 = pd.Series(dict(slider="55/60", curveball="50/50", changeup="40/40", cutter=None, command="50/50", tops=95))
    assert grade_fit(row2) == "bat-miss slider (60), strike-thrower"
