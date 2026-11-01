"""Unit tests for Step 5 execution metrics. Hand-built PAs check the definitions only."""
import numpy as np
import pandas as pd
import pytest

from src.execution import add_flags, entropy_bits, mixing, pa_table, pitcher_rates, sequences


def pa(game, ab, pitches, event, pitcher=1, stand="R"):
    """pitches: list of (pitch_type, description, type, zone). Counts are built from results."""
    rows, b, s = [], 0, 0
    for i, (pt, desc, typ, zone) in enumerate(pitches, start=1):
        last = i == len(pitches)
        rows.append(dict(game_pk=game, at_bat_number=ab, pitch_number=i, pitcher=pitcher,
                         player_name="P", p_throws="R", stand=stand, pitch_type=pt, description=desc,
                         type=typ, zone=zone, balls=b, strikes=s, events=event if last else None))
        if typ == "B":
            b += 1
        elif typ == "S" and not (desc.startswith("foul") and s == 2):
            s = min(s + 1, 2)
    return rows


CS = ("FF", "called_strike", "S", 5)
SW = ("SL", "swinging_strike", "S", 14)
FOUL = ("FF", "foul", "S", 2)
BALL = ("SL", "ball", "B", 13)
INPLAY = ("FF", "hit_into_play", "X", 5)


@pytest.fixture
def df():
    rows = (pa(1, 1, [CS, SW, SW], "strikeout")             # K in 3: F-strike, 3PS, 2-strike PA
            + pa(1, 2, [BALL, BALL, BALL, BALL], "walk")      # BB, no F-strike
            + pa(1, 3, [INPLAY], "field_out")                 # out on pitch 1 -> 3PS
            + pa(1, 4, [BALL, CS, FOUL, BALL, INPLAY], "single")  # 2 strikes after 3 -> 3PS, no K
            + pa(1, 5, [BALL, BALL, CS, FOUL, INPLAY], "double"))  # 2 strikes on pitch 5: not 3PS
    return add_flags(pd.DataFrame(rows))


def test_pa_level_definitions(df):
    p = pa_table(df).set_index("at_bat_number")
    assert p["first_strike"].tolist() == [True, False, True, False, False]
    assert p["three_ps"].tolist() == [True, False, True, True, False]
    assert p["reached_two"].tolist() == [True, False, False, True, True]
    assert p["k"].sum() == 1 and p["bb"].sum() == 1


def test_pitcher_rates(df):
    r = pitcher_rates(df, pa_table(df)).iloc[0]
    assert r["pa"] == 5
    assert r["f_strike_pct"] == 40.0
    assert r["three_ps_pct"] == 60.0
    assert r["kill_pct"] == pytest.approx(33.3)
    assert r["k_pct"] == 20.0 and r["bb_pct"] == 20.0 and r["k_bb_pct"] == 0.0
    # 18 pitches: in zone = CS x3, FOUL x2, INPLAY x3 = 8 -> 44.4%
    assert r["zone_pct"] == pytest.approx(44.4)
    # swings: SW x2, FOUL x2, INPLAY x3 = 7; whiffs 2
    assert r["whiff_pct"] == pytest.approx(28.6)
    # out of zone: SW x2 + BALL x8 = 10, chases = 2
    assert r["chase_pct"] == 20.0
    # CSW = (3 called + 2 whiffs) / 18
    assert r["csw_pct"] == pytest.approx(27.8)


def test_count_state(df):
    first = df[df["at_bat_number"] == 1]["count_state"].tolist()
    assert first == ["even", "ahead", "two_strikes"]
    assert df[(df["at_bat_number"] == 2) & (df["pitch_number"] == 2)]["count_state"].item() == "behind"


def test_entropy_bits():
    assert entropy_bits(pd.Series([10, 10])) == pytest.approx(1.0)
    assert entropy_bits(pd.Series([5, 5, 5, 5])) == pytest.approx(2.0)
    assert entropy_bits(pd.Series([7])) == pytest.approx(0.0)


def test_mixing_two_strike_top_pitch(df):
    m = mixing(df).iloc[0]
    # two-strike pitches: PA1 SL (whiff), PA4 SL ball + FF in play, PA5 FF in play -> 2 SL, 2 FF
    assert m["two_strike_top_pitch"] in {"SL", "FF"}
    assert m["two_strike_top_share"] == 50.0


def test_sequences_repeat_rate_and_top_seq(df):
    rep, summ = sequences(df)
    # 13 back-to-back pairs (2 + 3 + 0 + 4 + 4); repeats: 1 + 3 + 0 + 1 + 3 = 8
    assert rep.loc[0, "back_to_back_same_pct"] == pytest.approx(100 * 8 / 13, abs=0.1)
    assert rep.loc[0, "top_seq_1"] == "SL->SL"
