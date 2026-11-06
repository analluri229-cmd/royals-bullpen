"""Collect pitch clips through your browser and file them under the right pitcher and pitch type.

MLB returns 403 to scripted downloads, so this helper doesn't download anything itself. It does
everything around the download:

  1. collect (default): for each clip src.fetch_clips picked but couldn't download, it prints the
     label (pitcher, pitch type, date, at-bat, pitch), opens the Savant link in your browser, and
     waits. Save the video (right-click > Save video as, any name, Downloads or data/manual), then
     press Enter. It finds the new .mp4, moves it to outputs/clips/<pitcher>/<PT>_<game>_<ab>_<pitch>.mp4
     and marks it in the manifest. The label comes from the pitch it picked, so you never type it.
  2. --sort: for loose .mp4 files you already saved (Downloads, data/manual), it asks for each one:
     which pitcher and which pitch type, then moves and renames it the same way.

Usage (run from the project folder in VS Code):
  python -m src.fetch_clips --pitchers "Erceg, Lucas"     # picks the pitches (first time)
  python -m src.collect_clips                             # open, save, auto-file
  python -m src.collect_clips --pitcher "Erceg, Lucas"    # just one pitcher
  python -m src.collect_clips --sort                      # file clips you already saved
  python -m src.collect_clips --watch "D:/Clips"          # also look in another folder
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
import webbrowser
from pathlib import Path

import numpy as np
import pandas as pd

from src import fetch_clips as fc
from src.pitch_overlay import PITCH_NAMES
from src.stuff import PITCH_GROUPS

PITCH_CHOICES = ["FF", "SI", "FC", "SL", "ST", "SV", "CU", "KC", "CH", "FS", "FO"]
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}


def default_watch_dirs() -> list[Path]:
    return [Path.home() / "Downloads", fc.ROOT / "data" / "manual"]


def videos_in(dirs: list[Path], since: float = 0.0) -> list[Path]:
    """Video files in these folders modified at or after `since`, newest first (skips partial downloads)."""
    out = []
    for d in dirs:
        if d.is_dir():
            out += [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT
                    and p.stat().st_mtime >= since]
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def pending(man: pd.DataFrame, pitcher: str | None = None) -> pd.DataFrame:
    """Manifest rows that have a link but no clip file yet."""
    m = man if pitcher is None else man[man["name"] == pitcher]
    has_link = m["source_url"].astype(str).str.startswith("http")
    missing = ~m["path"].astype(str).map(lambda p: (fc.ROOT / p).exists())
    return m[has_link & missing]


def file_clip(src: Path, dest: Path) -> Path:
    """Move a saved clip into place (keeps the original extension)."""
    dest = dest.with_suffix(src.suffix.lower())
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), dest)
    return dest


def label(r) -> str:
    parts = [str(r.name), f"{r.pitch_type} ({PITCH_NAMES.get(r.pitch_type, r.pitch_type)})"]
    if pd.notna(r.game_date):
        parts.append(str(r.game_date)[:10])
    if pd.notna(r.at_bat_number):
        parts.append(f"at-bat {int(r.at_bat_number)}, pitch {int(r.pitch_number)}")
    if pd.notna(r.release_speed):
        parts.append(f"{r.release_speed} mph")
    return " | ".join(parts)


def choose(prompt: str, options: list[str], ask=input) -> str | None:
    """Numbered pick (or type the value). Blank = skip."""
    for i, o in enumerate(options, 1):
        print(f"  {i}. {o}")
    ans = ask(prompt).strip()
    if not ans:
        return None
    if ans.isdigit() and 1 <= int(ans) <= len(options):
        return options[int(ans) - 1]
    return ans


def wait_for_clip(dirs: list[Path], since: float, ask=input) -> Path | None:
    """After the user saves the video and presses Enter: the new file, or the one they pick / type."""
    while True:
        ans = ask("  Saved it? Enter = find it, s = skip, or paste the file path: ").strip().strip('"')
        if ans.lower() == "s":
            return None
        if ans:
            p = Path(ans)
            if p.exists():
                return p
            print("  not found:", p)
            continue
        new = videos_in(dirs, since)
        if len(new) == 1:
            return new[0]
        if len(new) > 1:
            pick = choose("  Several new videos. Which one? ", [p.name for p in new], ask)
            hit = [p for p in new if p.name == pick]
            if hit:
                return hit[0]
            continue
        print("  No new video yet in:", ", ".join(str(d) for d in dirs))


def collect(man: pd.DataFrame, dirs: list[Path], pitcher: str | None = None, ask=input,
            open_url=webbrowser.open) -> pd.DataFrame:
    todo = pending(man, pitcher)
    if todo.empty:
        print("Nothing to collect: every picked clip is already filed (or has no link).")
        return man
    print(f"{len(todo)} clip(s) to collect. Save each one anywhere in: " + ", ".join(str(d) for d in dirs))
    for i, r in todo.iterrows():
        print("\n" + label(r))
        since = time.time() - 1
        open_url(r.source_url)
        src = wait_for_clip(dirs, since, ask)
        if src is None:
            print("  skipped")
            continue
        dest = file_clip(src, fc.ROOT / r.path)
        man.at[i, "path"] = str(dest.relative_to(fc.ROOT)).replace("\\", "/")
        print("  filed ->", man.at[i, "path"])
    return man


def sort_loose(man: pd.DataFrame, dirs: list[Path], ask=input) -> pd.DataFrame:
    """Ask pitcher + pitch type for each loose video, then move and rename it."""
    files = videos_in(dirs)
    if not files:
        print("No loose videos in:", ", ".join(str(d) for d in dirs))
        return man
    names = sorted(set(man["name"].dropna())) if not man.empty else []
    if not names:
        names = sorted(fc.default_pitchers().values())
    for f in files:
        print(f"\n{f}")
        who = choose("  Pitcher (number or 'Last, First', blank = skip): ", names, ask)
        if not who:
            continue
        pt = (ask(f"  Pitch type {'/'.join(PITCH_CHOICES)}: ").strip().upper() or None)
        if pt is None:
            continue
        ids = man.loc[man["name"] == who, "pitcher"].dropna()
        pid = int(ids.iloc[0]) if len(ids) else None
        dest = fc.CLIPS_DIR / fc.slug(who) / f"{pt}_{fc.slug(f.stem)[:60]}.mp4"
        dest = file_clip(f, dest)
        print("  filed ->", dest.relative_to(fc.ROOT))
        row = dict(pitcher=pid, name=who, pitch_type=pt, is_primary_fb=PITCH_GROUPS.get(pt) == "FB",
                   source_url=str(f), path=str(dest.relative_to(fc.ROOT)).replace("\\", "/"), release_sec=np.nan)
        man.loc[len(man)] = [row.get(c, np.nan) for c in man.columns]  # in place, so Ctrl+C keeps it
    return man


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pitcher", help='only this pitcher, "Last, First"')
    ap.add_argument("--sort", action="store_true", help="file videos you already saved (asks pitcher + type)")
    ap.add_argument("--watch", nargs="*", type=Path, default=[], help="extra folders to look in")
    a = ap.parse_args(argv)
    dirs = default_watch_dirs() + list(a.watch)
    fc.CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    man = pd.read_csv(fc.MANIFEST) if fc.MANIFEST.exists() else pd.DataFrame(columns=fc.MANIFEST_COLS)
    man = man.reindex(columns=fc.MANIFEST_COLS).reset_index(drop=True)
    man = man.astype({c: object for c in ("name", "pitch_type", "source_url", "path", "is_primary_fb")})
    try:
        man = sort_loose(man, dirs) if a.sort else collect(man, dirs, a.pitcher)
    finally:
        man.to_csv(fc.MANIFEST, index=False)  # keep whatever got filed, even on Ctrl+C
    print(f"\nmanifest: {fc.MANIFEST.relative_to(fc.ROOT)}. Next: python -m src.pitch_overlay --pitcher \"...\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
