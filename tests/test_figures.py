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
