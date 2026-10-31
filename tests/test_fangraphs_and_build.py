"""Unit tests for Step 2 ranking/cleanup and the Step 3 parquet build helpers."""
import pandas as pd
import pytest

from src.build_statcast_parquet import combine, select_columns
from src.config import KEEP_COLUMNS
from src.fangraphs import RANK_STATS, merge_tabs, normalize, rank_teams
from src.split_fg_workbooks import tab_slug


def test_rank_direction_and_ties():
    df = pd.DataFrame({"Team": ["A", "B", "C"], "ERA": [3.0, 4.5, 3.0],
                       "WAR": [5.0, 1.0, 3.0], "BB%": [8.0, 10.0, 9.0]})
    r = rank_teams(df, RANK_STATS).set_index("Team")
    assert r.loc["A", "ERA_rank"] == 1 and r.loc["C", "ERA_rank"] == 1 and r.loc["B", "ERA_rank"] == 3
    assert list(r["WAR_rank"]) == [1, 3, 2]
    assert list(r["BB%_rank"]) == [1, 3, 2]


def test_normalize_percent_strings_and_fractions():
    manual = normalize(pd.DataFrame({"Team": ["KCR"], "K%": ["22.5 %"], "BB%": ["9.0 %"]}))
    assert manual.loc[0, "K%"] == 22.5 and manual.loc[0, "K-BB%"] == pytest.approx(13.5)
    api = normalize(pd.DataFrame({"TeamName": ["KCR"], "K%": [0.225], "BB%": [0.09],
                                  "K-BB%": [0.135]}))
    assert api.loc[0, "Team"] == "KCR" and api.loc[0, "K-BB%"] == pytest.approx(13.5)
    noisy = normalize(pd.DataFrame({"Team": ["LAD"], "K%": [0.262], "BB%": [0.099]}))
    assert noisy.loc[0, "K%"] == 26.2 and noisy.loc[0, "BB%"] == 9.9 and noisy.loc[0, "K-BB%"] == 16.3


def test_merge_tabs_joins_on_name_and_team_keeps_first_copy():
    dash = pd.DataFrame({"#": [1, 2], "Name": ["A", "A"], "Team": ["KCR", "2 Tms"],
                         "ERA": [3.0, 4.0], "WAR": [1.0, 0.5]})
    adv = pd.DataFrame({"#": [1, 2], "Name": ["A", "A"], "Team": ["2 Tms", "KCR"],
                        "ERA": [9.9, 9.9], "K%": [0.20, 0.25]})
    out = merge_tabs([dash, adv]).set_index("Team")
    assert out.loc["KCR", "K%"] == 0.25 and out.loc["2 Tms", "K%"] == 0.20
    assert out.loc["KCR", "ERA"] == 3.0 and list(out.columns).count("ERA") == 1


def test_tab_slug():
    assert [tab_slug(s) for s in ("Stuff+", "Stuff", "Location+", "Dashboard")] == \
        ["stuff_plus", "stuff", "location_plus", "dashboard"]


def test_select_columns_requires_keep_list():
    with pytest.raises(ValueError):
        select_columns(KEEP_COLUMNS[:-1])
    assert select_columns(KEEP_COLUMNS + ["umpire", "junk"])[-1] == "umpire"


def test_combine_dedupes_pitches_across_files():
    base = {c: [None] for c in KEEP_COLUMNS}
    a = pd.DataFrame({**base, "game_pk": [1], "at_bat_number": [1], "pitch_number": [1],
                      "game_date": ["2026-04-01"], "release_speed": [95.0]})
    b = a.copy()
    c = a.assign(pitch_number=[2])
    out = combine([a, b, c])
    assert len(out) == 2 and out["pitch_number"].tolist() == [1, 2]
