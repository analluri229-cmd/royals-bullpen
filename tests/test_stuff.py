"""Unit tests for Step 4 Stuff metrics (VAA, LiVAA, percentiles, Stuff+ join).

The small frames here check formulas and logic only; they are never analyzed.
"""
import numpy as np
import pandas as pd
import pytest

from src.stuff import (PLATE_FRONT_Y, START_Y, add_livaa, add_percentiles, add_pitch_physics,
                       join_stuff_plus, livaa_fit, name_key, summarize, vaa)


def vaa_by_kinematics(vy0, vz0, ay, az):
    """Independent check: solve y(t) = 17/12 for t, then angle of (vy, vz) at t."""
    # START_Y + vy0 t + ay t^2 / 2 = PLATE_FRONT_Y  (vy0 < 0, ball moving toward plate)
    a, b, c = ay / 2, vy0, START_Y - PLATE_FRONT_Y
    t = (-b - np.sqrt(b * b - 4 * a * c)) / (2 * a)
    vy, vz = vy0 + ay * t, vz0 + az * t
    return np.degrees(np.arctan2(vz, -vy))


@pytest.mark.parametrize("vy0,vz0,ay,az", [
    (-138.0, -6.0, 28.0, -14.0),    # riding four-seamer
    (-126.0, -3.0, 24.0, -30.0),    # curveball
    (-132.0, -5.0, 26.0, -24.0),    # changeup
])
def test_vaa_matches_kinematics(vy0, vz0, ay, az):
    assert vaa(vy0, vz0, ay, az) == pytest.approx(vaa_by_kinematics(vy0, vz0, ay, az), abs=1e-9)


def test_vaa_is_negative_and_steeper_for_more_drop():
    ff = vaa(-138.0, -6.0, 28.0, -14.0)
    cu = vaa(-126.0, -3.0, 24.0, -30.0)
    assert -7 < ff < -3 and cu < ff


def pitches(**cols):
    n = len(next(iter(cols.values())))
    base = dict(pitcher=[1] * n, player_name=["Lange, Alex"] * n, p_throws=["R"] * n,
                pitch_type=["FF"] * n, release_speed=[96.0] * n, pfx_x=[-0.5] * n,
                pfx_z=[1.4] * n, arm_angle=[40.0] * n, release_pos_z=[6.0] * n,
                release_pos_x=[-2.0] * n, release_extension=[6.5] * n, plate_z=[2.5] * n,
                vy0=[-138.0] * n, vz0=[-6.0] * n, ay=[28.0] * n, az=[-14.0] * n)
    base.update(cols)
    return pd.DataFrame(base)


def test_ivb_hb_in_inches_and_groups():
    df = add_pitch_physics(pitches(pitch_type=["FF", "ST", "FS"], pfx_x=[-0.5, 1.0, -0.8],
                                   pfx_z=[1.4, 0.1, 0.3]))
    assert df["ivb"].tolist() == pytest.approx([16.8, 1.2, 3.6])
    assert df["hb"].tolist() == pytest.approx([-6.0, 12.0, -9.6])
    assert df["pitch_group"].tolist() == ["FB", "BRK", "OFF"]


def test_livaa_removes_height_effect():
    z = np.linspace(1.0, 4.0, 40)
    df = pd.DataFrame({"pitch_group": "FB", "plate_z": z, "vaa": -6.5 + 0.8 * z})
    fit = livaa_fit(df)
    assert fit.loc[0, "slope"] == pytest.approx(0.8)
    out = add_livaa(df, fit)
    # perfectly linear in height -> LiVAA is the same for every pitch
    assert out["livaa"].std() == pytest.approx(0, abs=1e-9)
    assert out["livaa"].mean() == pytest.approx(out["vaa"].mean())


def test_summarize_usage_and_sample_flag():
    df = add_pitch_physics(pitches(pitch_type=["FF"] * 60 + ["SL"] * 20,
                                   release_speed=[96.0] * 59 + [99.0] + [86.0] * 20))
    df["livaa"] = df["vaa"]
    tab = summarize(df).set_index("pitch_type")
    assert tab.loc["FF", "usage_pct"] == 75.0 and tab.loc["SL", "usage_pct"] == 25.0
    assert tab.loc["FF", "velo_max"] == 99.0
    assert tab.loc["FF", "sample_flag"] == "" and tab.loc["SL", "sample_flag"] == "insufficient sample"


def test_percentiles_same_type_and_hand_only():
    tab = pd.DataFrame({
        "pitcher": [1, 2, 3, 4, 5],
        "pitch_type": ["FF", "FF", "FF", "FF", "FF"],
        "throws": ["R", "R", "R", "L", "R"],
        "velo": [94.0, 96.0, 98.0, 90.0, 99.0],
        "sample_flag": ["", "", "", "", "insufficient sample"],
    })
    out = add_percentiles(tab, qualified_ids=[1, 2, 3, 4]).set_index("pitcher")["velo_pctile"]
    assert out[1] == pytest.approx(100 * 0.5 / 3, abs=0.1)   # lowest of 3 RHP
    assert out[2] == 50.0
    assert out[3] == pytest.approx(100 * 2.5 / 3, abs=0.1)
    assert out[4] == 50.0            # only lefty: compared with himself
    assert np.isnan(out[5])          # under 50 pitches: no percentile


def test_name_key():
    assert name_key("Lynch IV, Daniel") == name_key("Daniel Lynch IV") == "daniellynch"
    assert name_key("Avila, Luinder") == name_key("Luinder Ávila")


def test_join_stuff_plus_by_name_and_code_map():
    tab = pd.DataFrame({"pitcher": [1, 1, 1], "name": ["Lange, Alex"] * 3,
                        "pitch_type": ["FF", "ST", "KC"]})
    fg = pd.DataFrame({"Name": ["Alex Lange"], "Stuff+": [104], "Stf+ FA": [98],
                       "Stf+ SL": [121], "Stf+ CU": [110], "Stf+ KC": [115]})
    out = join_stuff_plus(tab, fg).set_index("pitch_type")
    assert out.loc["FF", "stuff_plus"] == 98
    assert out.loc["ST", "stuff_plus"] == 121      # FanGraphs folds sweepers into SL
    assert out.loc["KC", "stuff_plus"] == 115      # exact KC beats CU -> KC
    assert set(out["stuff_plus_overall"]) == {104}


def test_join_stuff_plus_prefers_mlbam_id():
    tab = pd.DataFrame({"pitcher": [7], "name": ["Smith, Will"], "pitch_type": ["FF"]})
    fg = pd.DataFrame({"Name": ["Will Smith", "Will Smith"], "MLBAMID": [8, 7],
                       "Stf+ FA": [90, 112]})
    assert join_stuff_plus(tab, fg).loc[0, "stuff_plus"] == 112


def test_join_stuff_plus_without_fangraphs():
    tab = pd.DataFrame({"pitcher": [1], "name": ["X"], "pitch_type": ["FF"]})
    assert np.isnan(join_stuff_plus(tab, None).loc[0, "stuff_plus"])


def test_summarize_drops_eephus_and_pitchouts():
    df = add_pitch_physics(pitches(pitch_type=["FF"] * 3 + ["EP", "PO", "FA"]))
    df["livaa"] = df["vaa"]
    tab = summarize(df)
    assert tab["pitch_type"].tolist() == ["FF"] and tab["usage_pct"].tolist() == [100.0]
