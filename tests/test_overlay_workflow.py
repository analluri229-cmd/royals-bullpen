"""The workflow runner calls the right scripts with the right arguments (scripts stubbed out)."""
import pytest

from src import overlay_workflow as ow


@pytest.fixture
def calls(tmp_path, monkeypatch):
    log = []
    monkeypatch.setattr(ow, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(ow.fetch_clips, "main", lambda argv: log.append(("fetch", argv)))
    monkeypatch.setattr(ow.collect_clips, "main", lambda argv: log.append(("collect", argv)))
    monkeypatch.setattr(ow.pitch_overlay, "main", lambda argv: log.append(("overlay", argv)))
    return log


def test_parse_box():
    assert ow.parse_box("0.05, 0.35 0.55 0.95") == [0.05, 0.35, 0.55, 0.95]
    assert ow.parse_box("") is None
    with pytest.raises(ValueError):
        ow.parse_box("0.6 0.3 0.2 0.9")


def test_full_run_with_answers(calls):
    answers = iter(["", "", "", "", "", "0.1 0.2 0.6 0.9", "30"])  # 4 steps yes, Enter, box, blur
    ow.main(["--pitchers", "Fairbanks, Pete"], ask=lambda _: next(answers))
    assert calls[0] == ("fetch", ["--pitchers", "Fairbanks, Pete"])
    assert calls[1] == ("collect", ["--pitcher", "Fairbanks, Pete"])
    assert calls[2] == ("overlay", ["--pitcher", "Fairbanks, Pete", "--sheet"])
    assert calls[3] == ("overlay", ["--pitcher", "Fairbanks, Pete", "--focus", "0.1", "0.2", "0.6", "0.9",
                                    "--blur", "30"])
    assert ow.load_settings()["Fairbanks, Pete"] == {"focus": [0.1, 0.2, 0.6, 0.9], "blur": 30}


def test_yes_mode_consistency_reuses_saved_box(calls):
    ow.save_settings({"Erceg, Lucas": {"focus": [0.1, 0.2, 0.6, 0.9], "blur": 20}})
    ow.main(["--pitchers", "Erceg, Lucas", "--same", "FF", "--yes"], ask=lambda _: pytest.fail("asked"))
    assert calls[0] == ("fetch", ["--pitchers", "Erceg, Lucas", "--same", "FF", "--n", "3"])
    assert calls[-1] == ("overlay", ["--pitcher", "Erceg, Lucas", "--same", "FF", "--focus", "0.1", "0.2", "0.6",
                                     "0.9", "--blur", "20"])


def test_skips_steps_answered_no(calls):
    answers = iter(["n", "n", "n", "", "none"])
    ow.main(["--pitchers", "Avila, Luinder"], ask=lambda _: next(answers))
    assert calls == [("overlay", ["--pitcher", "Avila, Luinder"])]
