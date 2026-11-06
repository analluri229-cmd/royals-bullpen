"""Browser-assisted clip collection: filing and sorting logic, with fake input and no browser."""
import os
import time

import numpy as np
import pandas as pd

from src import collect_clips as cc, fetch_clips as fc


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "ROOT", tmp_path)
    monkeypatch.setattr(fc, "CLIPS_DIR", tmp_path / "outputs" / "clips")
    dl = tmp_path / "Downloads"
    dl.mkdir()
    return dl


def manifest_row(**kw):
    base = dict(pitcher=1, name="Erceg, Lucas", pitch_type="FF", is_primary_fb=True, game_pk=7,
                game_date="2026-06-01", at_bat_number=12, pitch_number=3, stand="R", release_speed=97.1,
                pfx_x_in=-8.0, pfx_z_in=16.0, play_id="abc", source_url="https://baseballsavant.mlb.com/x",
                path="outputs/clips/erceg__lucas/FF_7_12_3.mp4", release_sec=np.nan)
    base.update(kw)
    return base


def test_collect_files_new_download_under_its_label(tmp_path, monkeypatch):
    dl = setup(tmp_path, monkeypatch)
    man = pd.DataFrame([manifest_row()])
    opened = []

    def fake_open(url):
        opened.append(url)
        time.sleep(0.05)
        (dl / "sporty_clip.mp4").write_bytes(b"video")

    out = cc.collect(man, [dl], ask=lambda _: "", open_url=fake_open)
    assert opened == ["https://baseballsavant.mlb.com/x"]
    assert (tmp_path / "outputs/clips/erceg__lucas/FF_7_12_3.mp4").read_bytes() == b"video"
    assert not (dl / "sporty_clip.mp4").exists()
    assert cc.pending(out).empty


def test_collect_skips_and_ignores_old_files(tmp_path, monkeypatch):
    dl = setup(tmp_path, monkeypatch)
    old = dl / "old.mp4"
    old.write_bytes(b"x")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    assert cc.videos_in([dl], since=time.time() - 60) == []
    man = pd.DataFrame([manifest_row()])
    answers = iter(["", "s"])  # nothing new yet, then skip
    cc.collect(man, [dl], ask=lambda _: next(answers), open_url=lambda u: None)
    assert old.exists() and len(cc.pending(man)) == 1


def test_sort_asks_pitcher_and_type(tmp_path, monkeypatch):
    dl = setup(tmp_path, monkeypatch)
    (dl / "erceg slider.mp4").write_bytes(b"v")
    man = pd.DataFrame([manifest_row()]).reindex(columns=fc.MANIFEST_COLS)
    man = man.astype({c: object for c in ("name", "pitch_type", "source_url", "path", "is_primary_fb")})
    answers = iter(["1", "sl"])
    out = cc.sort_loose(man, [dl], ask=lambda _: next(answers))
    new = out.iloc[-1]
    assert new["name"] == "Erceg, Lucas" and new["pitch_type"] == "SL" and new["pitcher"] == 1
    assert new["path"] == "outputs/clips/erceg__lucas/SL_erceg_slider.mp4"
    assert (tmp_path / new["path"]).exists() and not (dl / "erceg slider.mp4").exists()


def test_pending_skips_type_already_on_disk(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    have = tmp_path / "outputs/clips/erceg__lucas/FF_erceg_ff.mp4"
    have.parent.mkdir(parents=True)
    have.write_bytes(b"v")
    man = pd.DataFrame([manifest_row(), manifest_row(pitch_type="SL", path="outputs/clips/erceg__lucas/SL_7_20_1.mp4"),
                        manifest_row(source_url="data/manual/erceg_ff.mp4", path="outputs/clips/erceg__lucas/FF_erceg_ff.mp4")])
    assert list(cc.pending(man)["pitch_type"]) == ["SL"]
