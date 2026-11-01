"""Unit tests for Step 5A delivery and tunneling. Hand-built pitches check logic only."""
import numpy as np
import pandas as pd
import pytest

from src.deception import (build_pairs, delivery, flag_tunneled, good_pctile, position_at, rates,
                           tunnel_summary)
from src.stuff import PLATE_FRONT_Y, START_Y

FF = dict(vx0=6.0, vy0=-138.0, vz0=-6.0, ax=-10.0, ay=28.0, az=-14.0, plate_x=0.2, plate_z=2.8)
SL = dict(vx0=3.0, vy0=-126.0, vz0=-4.0, ax=6.0, ay=24.0, az=-30.0, plate_x=-0.6, plate_z=1.6)


def row(game, ab, num, ptype, pitcher=1, desc="ball", zone=12, **phys):
    base = dict(game_pk=game, at_bat_number=ab, pitch_number=num, pitcher=pitcher, player_name="P",
                p_throws="R", stand="R", pitch_type=ptype, description=desc, zone=zone,
                release_pos_x=-2.0, release_pos_z=6.0, release_extension=6.5, arm_angle=40.0)
    base.update(FF if ptype in ("FF", "SI") else SL)
    base.update(phys)
    return base


def test_position_at_plate_matches_plate_location():
    df = pd.DataFrame([FF, SL])
    x, z = position_at(df, PLATE_FRONT_Y)
    assert x == pytest.approx(df["plate_x"].to_numpy())
    assert z == pytest.approx(df["plate_z"].to_numpy())


def test_position_at_moves_along_path():
    df = pd.DataFrame([FF])
    x50, z50 = position_at(df, START_Y)
    x24, z24 = position_at(df, 23.8)
    xp, zp = position_at(df, PLATE_FRONT_Y)
    assert z50[0] > z24[0] > zp[0]  # ball drops on the way in


def test_pairs_only_back_to_back_different_types_same_pitcher():
    rows = [row(1, 1, 1, "FF"), row(1, 1, 2, "SL"), row(1, 1, 3, "SL"),  # FF->SL counts, SL->SL no
            row(1, 1, 4, "FF", pitcher=2),                                # pitching change: no
            row(1, 2, 1, "SL"), row(1, 2, 3, "FF")]                       # gap in pitch_number: no
    p = build_pairs(pd.DataFrame(rows))
    assert p["pair"].tolist() == ["FF->SL"]
    assert p.loc[0, "plate_in"] == pytest.approx(12 * np.hypot(0.8, 1.2))
    assert p.loc[0, "tunnel_in"] < p.loc[0, "plate_in"]


def test_identical_pitches_tunnel_perfectly():
    rows = [row(1, 1, 1, "FF"), row(1, 1, 2, "SI")]  # SI given same physics as FF
    p = build_pairs(pd.DataFrame(rows))
    assert p.loc[0, "tunnel_in"] == pytest.approx(0, abs=1e-9)
    assert p.loc[0, "plate_in"] == pytest.approx(0, abs=1e-9)


def test_flag_tunneled_below_league_median_and_rates():
    pairs = pd.DataFrame({"pitcher": 1, "player_name": "P", "p_throws": "R", "pair": "FF->SL",
                          "tunnel_in": [1.0, 2.0, 3.0, 4.0], "t20_in": 1.0, "t25_in": 1.0,
                          "plate_in": [10.0, 10.0, 10.0, 10.0], "break_tunnel_ratio": [10, 5, 3.3, 2.5],
                          "swing": [True, True, True, False], "whiff": [True, False, False, False],
                          "out_of_zone": [True, True, False, True]})
    f = flag_tunneled(pairs)
    assert f["tunneled"].tolist() == [True, True, False, False]
    s = tunnel_summary(f).iloc[0]
    assert s["tunnel_rate"] == 50.0
    assert s["tun_whiff_pct"] == 50.0 and s["tun_chase_pct"] == 100.0
    assert s["non_whiff_pct"] == 0.0 and s["non_chase_pct"] == 0.0
    assert s["sample_flag"] == "small sample"
    r = rates(f.iloc[3:4])
    assert np.isnan(r["whiff_pct"])  # no swings


def test_delivery_gap_and_within_2_inches():
    rows = [row(1, 1, i, "FF") for i in range(1, 7)]
    rows += [row(1, 2, i, "SL", release_pos_x=-2.0 + 3 / 12, arm_angle=34.0) for i in range(1, 5)]
    by_type, by_pitcher = delivery(pd.DataFrame(rows))
    sl = by_type.set_index("pitch_type").loc["SL"]
    assert sl["release_gap_in"] == pytest.approx(3.0)
    assert sl["gap_arm_deg"] == pytest.approx(6.0)
    p = by_pitcher.iloc[0]
    assert p["primary_fb"] == "FF"
    assert p["within_2in_pct"] == 60.0      # 6 of 10 pitches within 2 in of the FF release
    assert p["avg_release_gap_in"] == pytest.approx(3.0)


def test_good_pctile_smaller_is_better():
    out = good_pctile(pd.Series([1.0, 5.0, np.nan]), np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert out[0] == 90.0 and out[1] == 10.0 and np.isnan(out[2])
