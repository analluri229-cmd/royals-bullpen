"""One command for the whole pitch-overlay workflow: pick, collect, check, then make the videos.

It asks a few questions and runs the other scripts in order, so you don't have to remember them:

  1. pick      src.fetch_clips      picks the pitches (one of each type, or one type across the season)
  2. collect   src.collect_clips    opens each blocked link in your browser; you save it; it files it
  3. check     src.pitch_overlay --sheet   contact sheets + grid frame, to fix release times / pick a box
  4. make      src.pitch_overlay    the overlay video + still, one per pitcher

Each step asks first, so you can skip what is already done (Enter = yes, n = skip). Settings you type
for a pitcher (focus box, blur) are remembered in outputs/overlays/overlay_settings.json and offered
again next time.

Usage (from the project folder in VS Code):
  python -m src.overlay_workflow
  python -m src.overlay_workflow --pitchers "Fairbanks, Pete" "Morejon, Adrian"
  python -m src.overlay_workflow --pitchers "Erceg, Lucas" --same FF      # consistency overlay
  python -m src.overlay_workflow --yes                                     # don't ask, run every step
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src import collect_clips, fetch_clips, pitch_overlay
from src.config import ROOT

SETTINGS = ROOT / "outputs" / "overlays" / "overlay_settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(s: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")


def ask_yes(question: str, auto: bool, ask=input) -> bool:
    if auto:
        print(f"{question} yes")
        return True
    return ask(f"{question} [Y/n] ").strip().lower() not in ("n", "no", "s", "skip")


def parse_box(text: str) -> list[float] | None:
    """'0.05 0.35 0.55 0.95' (or with commas) -> 4 fractions; blank -> None."""
    parts = text.replace(",", " ").split()
    if not parts:
        return None
    vals = [float(v) for v in parts]
    if len(vals) != 4 or not all(0 <= v <= 1 for v in vals) or vals[2] <= vals[0] or vals[3] <= vals[1]:
        raise ValueError("need LEFT TOP RIGHT BOTTOM, fractions 0-1, left < right, top < bottom")
    return vals


def ask_box(name: str, saved: dict, auto: bool, ask=input) -> list[float] | None:
    prev = saved.get(name, {}).get("focus")
    if auto:
        return prev
    hint = f" (Enter = keep {' '.join(map(str, prev))}, 'none' = no blur)" if prev else " (Enter = no blur)"
    while True:
        ans = ask(f"  Focus box for {name}: LEFT TOP RIGHT BOTTOM from the grid frame{hint}: ").strip()
        if not ans:
            return prev
        if ans.lower() == "none":
            return None
        try:
            return parse_box(ans)
        except ValueError as exc:
            print("  ", exc)


def overlay_args(name: str, same: str | None, focus: list[float] | None, blur: int | None) -> list[str]:
    args = ["--pitcher", name]
    if same is not None:
        args += ["--same", same]
    if focus:
        args += ["--focus", *map(str, focus)]
        if blur:
            args += ["--blur", str(blur)]
    return args


def run_step(label: str, fn, argv: list[str]) -> bool:
    print(f"\n=== {label}: python -m {fn.__module__} {' '.join(argv)}")
    try:
        fn(argv)
        return True
    except SystemExit as exc:  # the scripts exit with a message when something is missing
        if exc.code not in (0, None):
            print(f"  stopped: {exc.code}")
        return exc.code in (0, None)
    except Exception as exc:  # keep going with the next pitcher / step
        print(f"  failed: {exc}")
        return False


def main(argv: list[str] | None = None, ask=input) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pitchers", nargs="*", help='names as "Last, First" (default: asks; Enter = KC relievers)')
    ap.add_argument("--same", nargs="?", const="FF", metavar="PT",
                    help="consistency overlay: one pitch type across the season (default FF)")
    ap.add_argument("--n", type=int, default=3, help="with --same: how many outings")
    ap.add_argument("--yes", action="store_true", help="run every step without asking")
    a = ap.parse_args(argv)

    names = a.pitchers
    if names is None and not a.yes:
        typed = ask('Pitchers, separated by ";" (e.g. Fairbanks, Pete; Morejon, Adrian). Enter = KC relievers: ')
        names = [n.strip() for n in typed.split(";") if n.strip()]
    pick = ["--pitchers", *names] if names else []
    if a.same:
        pick += ["--same", a.same, "--n", str(a.n)]

    if ask_yes("1. Pick the pitches (fetch_clips)?", a.yes, ask):
        run_step("pick", fetch_clips.main, pick)
    if ask_yes("2. Collect the clips in your browser (collect_clips)?", a.yes, ask):
        for nm in names or [None]:
            run_step("collect", collect_clips.main, ["--pitcher", nm] if nm else [])
    if not names:
        names = sorted(fetch_clips.default_pitchers().values())

    saved = load_settings()
    if ask_yes("3. Make contact sheets to check release times and pick a blur box?", a.yes, ask):
        for nm in names:
            run_step(f"sheets {nm}", pitch_overlay.main, overlay_args(nm, a.same, None, None) + ["--sheet"])
        print("\nIf a release guess is wrong (replay, cut-away), type the right time into release_sec in"
              f" {fetch_clips.MANIFEST.relative_to(ROOT)} now, then come back here.")
        if not a.yes:
            ask("Press Enter when you're ready to make the overlays. ")

    if ask_yes("4. Make the overlay videos?", a.yes, ask):
        made = []
        for nm in names:
            focus = ask_box(nm, saved, a.yes, ask)
            blur = saved.get(nm, {}).get("blur", 18)
            if focus and not a.yes:
                b = ask(f"  Blur strength (Enter = {blur}): ").strip()
                blur = int(b) if b.isdigit() else blur
            saved[nm] = {"focus": focus, "blur": blur}
            save_settings(saved)
            if run_step(f"overlay {nm}", pitch_overlay.main, overlay_args(nm, a.same, focus, blur)):
                made.append(nm)
        print(f"\nDone: {len(made)} of {len(names)} overlays in outputs/overlays"
              + (f" (missing: {', '.join(n for n in names if n not in made)})" if len(made) < len(names) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
