"""Unit tests for Step 1 (pitching team, relief flag, relief IP, thresholds).

The fixtures are tiny hand-built games that check the logic; they are test
inputs only and are never used in the analysis.
"""
import pandas as pd
import pytest

from src.relievers import (add_pitching_team, add_relief_flag, ip_display, pa_outs,
                           summarize_relievers)


def pitch(game, ab, num, pitcher, inning, half, outs, events=None,
          home="KC", away="NYY", name=None):
    return dict(game_pk=game, at_bat_number=ab, pitch_number=num, pitcher=pitcher,
                player_name=name or f"P{pitcher}", p_throws="R", inning=inning,
                inning_topbot=half, outs_when_up=outs, events=events,
                home_team=home, away_team=away)


def frame(rows):
    df = pd.DataFrame(rows)
    df["inning_topbot"] = df["inning_topbot"].astype("string")
    df["events"] = df["events"].astype("string")
    return add_relief_flag(add_pitching_team(df))


@pytest.fixture
def game():
    # KC home. Top 1: KC starter 10 gets 3 outs. Bottom 1: NYY starter 20.
    # Top 2: KC reliever 11 relieves; NYY reliever 21 in bottom 2.
    rows = [
        pitch(1, 1, 1, 10, 1, "Top", 0, "strikeout"),
        pitch(1, 2, 1, 10, 1, "Top", 1), pitch(1, 2, 2, 10, 1, "Top", 1, "single"),
        pitch(1, 3, 1, 10, 1, "Top", 1, "grounded_into_double_play"),
        pitch(1, 4, 1, 20, 1, "Bot", 0, "field_out"),
        pitch(1, 5, 1, 20, 1, "Bot", 1, "walk"),
        pitch(1, 6, 1, 21, 1, "Bot", 1, "double_play"),
        pitch(1, 7, 1, 11, 2, "Top", 0, "home_run"),
        pitch(1, 8, 1, 11, 2, "Top", 0, "strikeout"),
        pitch(1, 9, 1, 12, 2, "Top", 1, "field_out"),
        pitch(1, 10, 1, 12, 2, "Top", 2, "strikeout"),
    ]
    return frame(rows)


def test_pitching_team_home_pitches_top(game):
    top = game[game.inning_topbot == "Top"]
    bot = game[game.inning_topbot == "Bot"]
    assert set(top.pitching_team) == {"KC"} and set(top.batting_team) == {"NYY"}
    assert set(bot.pitching_team) == {"NYY"}


def test_relief_flag_first_pitcher_per_team(game):
    flag = game.groupby("pitcher")["is_relief"].first().to_dict()
    assert flag == {10: False, 20: False, 21: True, 11: True, 12: True}


def test_first_pitcher_uses_order_not_row_position(game):
    shuffled = game.drop(columns=["is_relief"]).sample(frac=1, random_state=0)
    again = add_relief_flag(shuffled)
    assert again.groupby("pitcher")["is_relief"].first().to_dict() == \
        game.groupby("pitcher")["is_relief"].first().to_dict()


def test_outs_from_outs_diff(game):
    pa = pa_outs(game).set_index("at_bat_number")["outs"]
    assert pa[1] == 1 and pa[2] == 0 and pa[3] == 2       # top 1 = 3 outs
    assert pa[4] == 1 and pa[5] == 0 and pa[6] == 2       # bottom 1
    assert pa[7] == 0 and pa[8] == 1 and pa[9] == 1 and pa[10] == 1


def test_walkoff_final_half_uses_events():
    rows = [
        pitch(2, 1, 1, 30, 9, "Top", 0, "strikeout", home="KC"),
        pitch(2, 2, 1, 30, 9, "Top", 1, "field_out", home="KC"),
        pitch(2, 3, 1, 30, 9, "Top", 2, "strikeout", home="KC"),
        pitch(2, 4, 1, 40, 9, "Bot", 0, "field_out", home="KC"),
        pitch(2, 5, 1, 41, 9, "Bot", 1, "home_run", home="KC"),  # walk-off
    ]
    pa = pa_outs(frame(rows)).set_index("at_bat_number")["outs"]
    assert pa[3] == 1
    assert pa[4] == 1
    assert pa[5] == 0  # not 3 - 1 = 2


def test_summary_kc_only_and_ip(game):
    kc = summarize_relievers(game, team="KC").set_index("pitcher")
    assert set(kc.index) == {11, 12}
    assert kc.loc[11, "relief_outs"] == 1 and kc.loc[12, "relief_outs"] == 2
    assert kc.loc[12, "relief_ip_display"] == "0.2"
    assert kc.loc[11, "relief_bf"] == 2
    assert not kc["qualified"].any() and set(kc["sample_flag"]) == {"small sample"}


def test_qualifies_on_pitches_or_ip(monkeypatch):
    import src.relievers as r
    rows = [pitch(3, 1, 1, 50, 1, "Top", 0, "strikeout")]
    rows += [pitch(3, 2, i, 51, 1, "Top", 1) for i in range(1, 4)]
    rows += [pitch(3, 2, 4, 51, 1, "Top", 1, "field_out"),
             pitch(3, 3, 1, 51, 1, "Top", 2, "strikeout")]
    df = frame(rows)
    monkeypatch.setattr(r, "MIN_RELIEF_PITCHES", 5)
    monkeypatch.setattr(r, "MIN_RELIEF_IP", 100)
    assert bool(r.summarize_relievers(df).set_index("pitcher").loc[51, "qualified"])
    monkeypatch.setattr(r, "MIN_RELIEF_PITCHES", 500)
    monkeypatch.setattr(r, "MIN_RELIEF_IP", 0.6)
    assert bool(r.summarize_relievers(df).set_index("pitcher").loc[51, "qualified"])
    monkeypatch.setattr(r, "MIN_RELIEF_IP", 0.7)
    assert not bool(r.summarize_relievers(df).set_index("pitcher").loc[51, "qualified"])


@pytest.mark.parametrize("outs,shown", [(0, "0.0"), (1, "0.1"), (2, "0.2"), (3, "1.0"), (62, "20.2")])
def test_ip_display(outs, shown):
    assert ip_display(outs) == shown
