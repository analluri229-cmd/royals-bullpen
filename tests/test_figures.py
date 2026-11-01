"""Smoke tests for Step 8 figures: tiny frames, check that files are written at 300 dpi."""
import pandas as pd
import pytest

pytest.importorskip("matplotlib")
from src import figures  # noqa: E402


def test_short():
    assert figures.short("Lynch IV, Daniel") == "Lynch IV"


def test_slide1_writes_png(tmp_path, monkeypatch):
    monkeypatch.setattr(figures, "OUT_FIGS", tmp_path)
    ranks = pd.DataFrame({"Team": ["AAA", "KCR", "BBB"], "K-BB%": [15, 8, 12], "K-BB%_rank": [1, 3, 2],
                          "xFIP": [3.8, 4.8, 4.1], "xFIP_rank": [1, 3, 2], "WAR": [6, -3, 2], "WAR_rank": [1, 3, 2]})
    p = figures.slide1_ranks(ranks, "KCR")
    assert p.exists() and p.stat().st_size > 10_000
    from PIL import Image
    assert round(Image.open(p).info["dpi"][0]) == 300


def test_delivery_overlay_writes_png(tmp_path, monkeypatch):
    monkeypatch.setattr(figures, "OUT_FIGS", tmp_path)
    dp = pd.DataFrame([dict(name="A, B", throws="R", pitch_type=pt, n_pitches=100, rx_mean=-20 + i, rz_mean=70,
                            sd_side_in=1.5, sd_height_in=1.0, arm_mean=40, release_gap_in=float(i))
                       for i, pt in enumerate(["FF", "SL"])])
    dr = pd.DataFrame([dict(name="A, B", avg_release_gap_in=0.5, avg_release_gap_in_pctile=90.0)])
    assert figures.delivery_overlay(dp, dr, ["A, B"]).exists()


def test_headshot_file_name():
    from src.fetch_headshots import file_name
    assert file_name("Lynch IV, Daniel", 663738) == "lynch_iv__daniel_663738.png"


def test_arsenal_grid_writes_png(tmp_path, monkeypatch):
    monkeypatch.setattr(figures, "OUT_FIGS", tmp_path)
    stuff = pd.DataFrame([dict(pitcher=1, throws="R", pitch_type=pt, usage_pct=u, hb=hb, ivb=ivb, velo=v,
                               stuff_plus=sp, sample_flag=None)
                          for pt, u, hb, ivb, v, sp in [("FF", 60, -8, 16, 96.0, 110), ("SL", 40, 6, 0, 86.0, None)]])
    scores = pd.DataFrame({"pitcher": [1], "stuff_score": [70.0], "execution_score": [40.0]})
    p = figures.arsenal_grid(stuff, scores, pd.DataFrame({"pitcher": [1], "label": ["Test"]}), "t", "a.png")
    assert p.exists() and p.parent.name == "arsenal"
