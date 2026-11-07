"""Overlay video plumbing on tiny generated clips (moving square), not baseball data.

Checks: motion alignment recovers a known timing offset, the filtergraph trims each clip at its own
release, and a render writes an mp4 and a still.
"""
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from src import fetch_clips, pitch_overlay as po

HAS_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


def make_clip(path, move_at, seconds=4.0, fps=30, w=320, h=180):
    """Gray frames; a white square sweeps across for 0.5 s starting at move_at; hard cut to black at 3.2 s."""
    n = int(seconds * fps)
    frames = np.full((n, h, w, 3), 90, np.uint8)
    for k in range(n):
        t = k / fps
        if t >= 3.2:
            frames[k] = 0
            continue
        frac = min(max((t - move_at) / 0.5, 0), 1)
        x = int(20 + frac * (w - 80))
        frames[k, 60:120, x:x + 40] = 255
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, input=frames.tobytes(), check=True)
    return path


def test_layer_alphas_equal_mix():
    assert po.layer_alphas(1, None) == [0.5]
    assert po.layer_alphas(2, None) == [0.5, pytest.approx(1 / 3)]
    assert po.layer_alphas(2, 0.4) == [0.4, 0.4]


def test_filter_trims_each_clip_at_its_release():
    clips = [po.Clip(None, "FF", 2.0), po.Clip(None, "SL", 3.5)]
    f = po.build_filter(clips, [0.5], pre=1.0, post=0.5, speeds=[1.0, 0.5])
    assert "trim=start=1.000:duration=1.500" in f and "trim=start=2.500:duration=1.500" in f
    assert "colorchannelmixer=aa=0.500" in f and "concat=n=2" in f


def test_first_cut_and_guess():
    curve = np.r_[np.zeros(30), np.ones(10) * 5, np.zeros(20), [80], np.zeros(10)]
    assert po.first_cut(curve) == 60
    assert 30 <= po.guess_release(curve) * po.MOTION_FPS <= 40


@needs_ffmpeg
def test_align_recovers_offset(tmp_path):
    a = make_clip(tmp_path / "a.mp4", move_at=1.0)
    b = make_clip(tmp_path / "b.mp4", move_at=1.6)
    t = po.align_offset(po.motion_curve(a), po.motion_curve(b), base_release=1.2)
    assert abs(t - 1.8) <= 2 / po.MOTION_FPS


@needs_ffmpeg
def test_render_writes_video_and_still(tmp_path):
    a = make_clip(tmp_path / "a.mp4", move_at=1.0)
    b = make_clip(tmp_path / "b.mp4", move_at=1.6)
    clips = [po.Clip(a, "FF", 1.2, "96.0 mph"), po.Clip(b, "SL", None, "86.0 mph")]
    video, still, notes = po.render(clips, tmp_path / "o.mp4", "Test: four-seam vs slider", pre=0.8, post=0.6)
    assert video.exists() and still.exists() and video.stat().st_size > 1000
    assert any("aligned" in n for n in notes)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(video)], capture_output=True, text=True).stdout)
    assert dur == pytest.approx(1.4 + 1.4 / 0.35, abs=0.15)


def test_find_play_id():
    feed = {"liveData": {"plays": {"allPlays": [
        {"about": {"atBatIndex": 4}, "playEvents": [
            {"isPitch": False}, {"isPitch": True, "pitchNumber": 1, "playId": "x1"},
            {"isPitch": True, "pitchNumber": 2, "playId": "x2"}]}]}}}
    assert fetch_clips.find_play_id(feed, at_bat_number=5, pitch_number=2) == "x2"
    assert fetch_clips.find_play_id(feed, at_bat_number=4, pitch_number=2) is None


def test_find_mp4():
    html = '<video><source src="https:\\/\\/sporty-clips.mlb.com\\/abc\\/def.mp4" type="video/mp4"></video>'
    assert fetch_clips.find_mp4(html) == "https://sporty-clips.mlb.com/abc/def.mp4"


def test_select_clips_one_game_typical_pitch():
    rows = []
    for g in (1, 2):
        for k in range(60):
            rows.append(dict(game_pk=g, game_date="2026-06-01", at_bat_number=k // 4 + 1, pitch_number=k % 4 + 1,
                             pitcher=9, pitch_type="FF", stand="R", is_relief=True, release_speed=95 + (k % 3),
                             pfx_x=-0.7, pfx_z=1.3, release_pos_x=-2, release_pos_z=6))
    for k in range(60):  # sliders only in game 2
        rows.append(dict(game_pk=2, game_date="2026-06-01", at_bat_number=100 + k, pitch_number=1, pitcher=9,
                         pitch_type="SL", stand="R", is_relief=True, release_speed=85 + (k % 5) * 0.5,
                         pfx_x=0.4, pfx_z=0.1, release_pos_x=-2, release_pos_z=6))
    sel = fetch_clips.select_clips(pd.DataFrame(rows), {9: "Test, A"})
    assert list(sel["pitch_type"]) == ["FF", "SL"]
    assert set(sel["game_pk"]) == {2}
    assert sel.loc[sel["pitch_type"] == "FF", "release_speed"].iloc[0] == 96.0  # closest to mean


def test_add_file_and_blocked_list(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_clips, "CLIPS_DIR", tmp_path / "clips")
    monkeypatch.setattr(fetch_clips, "ROOT", tmp_path)
    monkeypatch.setattr(fetch_clips, "OPEN_IN_BROWSER", tmp_path / "clips" / "open_in_browser.txt")
    src = tmp_path / "Saved Clip.mp4"
    src.write_bytes(b"x")
    row = fetch_clips.add_file(src, "Erceg, Lucas", "SL", None)
    assert row.loc[0, "path"] == "clips/erceg__lucas/SL_saved_clip.mp4"
    assert (tmp_path / row.loc[0, "path"]).exists()
    (tmp_path / "clips").mkdir(exist_ok=True)
    fetch_clips.write_browser_list([("Erceg, Lucas", "SL", "https://x/y", "2026-06-01", 12, 3)])
    txt = (tmp_path / "clips" / "open_in_browser.txt").read_text()
    assert "https://x/y" in txt and '--pitcher "Erceg, Lucas" --pitch-type SL' in txt


def test_select_consistency_spreads_season_and_prefers_home():
    rows = []
    for m, month in enumerate(["2026-04-15", "2026-06-15", "2026-08-15"]):
        for k in range(30):
            rows.append(dict(game_pk=10 + m * 2 + (k % 2), game_date=month, at_bat_number=k + 1, pitch_number=1,
                             pitcher=9, pitch_type="FF", stand="R", is_relief=True,
                             home_team="KC" if k % 2 == 0 else "NYY", release_speed=96 + (k % 3) * 0.5,
                             pfx_x=-0.7, pfx_z=1.3, release_pos_x=-2, release_pos_z=6))
    sel = fetch_clips.select_consistency(pd.DataFrame(rows), {9: "Test, A"}, None, n=3)
    assert list(sel["game_date"]) == ["2026-04-15", "2026-06-15", "2026-08-15"]
    assert set(sel["set"]) == {"same_FF"} and (sel["game_pk"] % 2 == 0).all()  # home (even) games


def test_same_pitch_clips_orders_by_date(tmp_path, monkeypatch):
    monkeypatch.setattr(po, "ROOT", tmp_path)
    rows = []
    for d in ["2026-08-01", "2026-04-02"]:
        f = tmp_path / f"FF_{d}.mp4"
        f.write_bytes(b"v")
        rows.append(dict(name="Erceg, Lucas", pitch_type="FF", is_primary_fb=True, game_date=d, release_speed=97.0,
                         release_sec=None, path=f.name, set="same_FF"))
    clips = po.same_pitch_clips(pd.DataFrame(rows), "Erceg, Lucas", None)
    assert [c.note for c in clips] == ["Apr 2  97.0 mph", "Aug 1  97.0 mph"]


def test_repick_rejects_clip_and_takes_next_in_same_game(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_clips, "ROOT", tmp_path)
    bad = tmp_path / "SL_5_2_1.mp4"
    bad.write_bytes(b"v")
    base = dict(pitcher=9, name="Fairbanks, Pete", stand="R", source_url="https://x", release_sec=None)
    man = pd.DataFrame([dict(base, pitch_type="FF", game_pk=5, at_bat_number=1, pitch_number=1, path="FF.mp4", set=None),
                        dict(base, pitch_type="SL", game_pk=5, at_bat_number=2, pitch_number=1, path=bad.name, set=None)]
                       ).reindex(columns=fetch_clips.MANIFEST_COLS).astype({"set": object})
    rows = []
    for g in (5, 6):
        for ab in range(1, 6):
            rows.append(dict(game_pk=g, game_date="2026-07-01", at_bat_number=ab, pitch_number=1, pitcher=9,
                             pitch_type="SL", stand="R", is_relief=True, release_speed=85.0 + (ab == 2) * 0.0,
                             pfx_x=0.5, pfx_z=0.1 + 0.01 * ab, release_pos_x=-2, release_pos_z=6))
    man2, row = fetch_clips.repick(man, pd.DataFrame(rows), "Fairbanks, Pete", "SL")
    assert man2.loc[1, "set"] == "rejected" and (tmp_path / "SL_5_2_1.rejected.mp4").exists()
    assert row.at[0, "game_pk"] == 5 and row.at[0, "at_bat_number"] != 2
    from src import collect_clips
    monkeypatch.setattr(collect_clips.fc, "ROOT", tmp_path)
    assert "SL" not in set(collect_clips.pending(man2)["pitch_type"])  # rejected row not asked for again


def test_focus_blurs_outside_box():
    clips = [po.Clip(None, "FF", 2.0), po.Clip(None, "SL", 3.0)]
    f = po.build_filter(clips, [0.5], 1.0, 0.5, [1.0], focus=(0.1, 0.2, 0.6, 0.9))
    assert "boxblur=18:2" in f and "crop=640:504:128:144" in f and "overlay=128:144" in f
    with pytest.raises(SystemExit):
        po.focus_box((0.6, 0.2, 0.1, 0.9))


@needs_ffmpeg
def test_render_with_focus_and_grid(tmp_path):
    a = make_clip(tmp_path / "a.mp4", move_at=1.0)
    b = make_clip(tmp_path / "b.mp4", move_at=1.6)
    clips = [po.Clip(a, "FF", 1.2), po.Clip(b, "SL", 1.8)]
    video, still, _ = po.render(clips, tmp_path / "f.mp4", "t", pre=0.8, post=0.6, focus=(0.1, 0.1, 0.5, 0.9))
    assert video.exists() and still.exists()
    assert po.grid_frame(a, tmp_path / "g.png", 1.2).exists()


@needs_ffmpeg
def test_clip_duration(tmp_path):
    a = make_clip(tmp_path / "a.mp4", move_at=1.0, seconds=4.0)
    assert po.clip_duration(a) == pytest.approx(4.0, abs=0.1)
