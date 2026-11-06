"""Pick and download real pitch clips for the delivery video overlays (run on Windows; the cloud can't reach MLB).

For each pitcher, this picks ONE game where he threw his primary fastball and his secondaries,
then picks the most typical pitch of each type in that game (closest to his season average on
velocity, movement and release point). Using one game keeps the broadcast camera the same, which is
what makes the overlay line up.

Each pitch is looked up in the MLB Stats API game feed to get its playId, and the clip is downloaded
from Baseball Savant's video page. Files are cached: an existing clip is never downloaded again.

Output:
  outputs/clips/<pitcher_slug>/<PT>_<game_pk>_<ab>_<pitch>.mp4
  outputs/clips/clips_manifest.csv   one row per clip; fill in release_sec (or let
                                     src.pitch_overlay find it) before building overlays

You can also add any clip by hand (MLB Film Room, mlb.com/video, a Savant link):
  python -m src.fetch_clips --url "https://www.mlb.com/video/..." --pitcher "Erceg, Lucas" --pitch-type SL

Clips are MLB's. Fine for a private portfolio video; check MLB's terms before posting publicly.

Usage:
  python -m src.fetch_clips                                   # all qualified KC relievers
  python -m src.fetch_clips --pitchers "Erceg, Lucas" "Strahm, Matt"
  python -m src.fetch_clips --file "C:/Users/themi/Downloads/clip.mp4" --pitcher "Erceg, Lucas" --pitch-type SL
  python -m src.fetch_clips --pitchers "Erceg, Lucas" --same FF --n 3   # 3 fastballs across the season
  python -m src.fetch_clips --dry-run                         # pick pitches, don't download
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import shutil
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import MIN_PITCHES_PER_TYPE, OUT_TABLES, PITCHES_PARQUET, ROOT
from src.stuff import PITCH_GROUPS

CLIPS_DIR = ROOT / "outputs" / "clips"
MANIFEST = CLIPS_DIR / "clips_manifest.csv"
FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
SAVANT_VIDEO_URL = "https://baseballsavant.mlb.com/sporty-videos?playId={play_id}"
UA = {"User-Agent": "Mozilla/5.0"}
OPEN_IN_BROWSER = CLIPS_DIR / "open_in_browser.txt"
SHAPE_COLS = ["release_speed", "pfx_x", "pfx_z", "release_pos_x", "release_pos_z"]
MANIFEST_COLS = ["pitcher", "name", "pitch_type", "is_primary_fb", "game_pk", "game_date", "at_bat_number",
                 "pitch_number", "stand", "release_speed", "pfx_x_in", "pfx_z_in", "play_id", "source_url",
                 "path", "release_sec", "set"]


def slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(text).lower()).strip("_")


def pitch_types(p: pd.DataFrame, min_n: int = MIN_PITCHES_PER_TYPE) -> tuple[str, list[str]]:
    """Primary fastball (most-thrown FB) and the other pitch types with at least min_n pitches."""
    counts = p["pitch_type"].value_counts()
    counts = counts[counts >= min_n]
    fbs = [t for t in counts.index if PITCH_GROUPS.get(t) == "FB"]
    primary = fbs[0] if fbs else counts.index[0]
    return primary, [t for t in counts.index if t != primary]


def pick_game(p: pd.DataFrame, types: list[str]) -> int:
    """Game that covers the most of his pitch types (primary FB required), then the most pitches."""
    has = p[p["pitch_type"].isin(types)].groupby("game_pk")["pitch_type"].agg(["nunique", "size"])
    has["has_fb"] = p[p["pitch_type"] == types[0]].groupby("game_pk").size().reindex(has.index).fillna(0) > 0
    has = has[has["has_fb"]].sort_values(["nunique", "size"], ascending=False)
    if has.empty:
        raise ValueError("no game with his primary fastball")
    return int(has.index[0])


def typical_pitches(p: pd.DataFrame, game_pk: int, types: list[str]) -> pd.DataFrame:
    """In that game, the pitch of each type closest to his season average for that type.

    Distance is in season-SD units over velocity, movement and release point. Pitches to the same
    batter side as his fastball pick are preferred so the hitter stands in the same box.
    """
    rows = []
    g = p[p["game_pk"] == game_pk]
    fb_stand = None
    for t in types:
        season = p[p["pitch_type"] == t][SHAPE_COLS]
        cand = g[g["pitch_type"] == t].dropna(subset=SHAPE_COLS)
        if cand.empty:
            continue
        sd = season.std().replace(0, np.nan).fillna(1.0)
        dist = (((cand[SHAPE_COLS] - season.mean()) / sd) ** 2).sum(axis=1) ** 0.5
        if fb_stand is not None:
            dist = dist + np.where(cand["stand"] == fb_stand, 0.0, 1.0)
        best = cand.loc[dist.idxmin()]
        if fb_stand is None:
            fb_stand = best["stand"]
        rows.append(best)
    return pd.DataFrame(rows)


def select_clips(df: pd.DataFrame, pitcher_ids: dict[int, str]) -> pd.DataFrame:
    """One manifest row per pitcher x pitch type, all from one game per pitcher."""
    out = []
    for pid, name in pitcher_ids.items():
        p = df[(df["pitcher"] == pid) & df["is_relief"]] if "is_relief" in df else df[df["pitcher"] == pid]
        if p.empty:
            print("no pitches for", name)
            continue
        primary, secondaries = pitch_types(p)
        types = [primary] + secondaries
        game = pick_game(p, types)
        picks = typical_pitches(p, game, types)
        for r in picks.itertuples():
            out.append(dict(pitcher=pid, name=name, pitch_type=r.pitch_type, is_primary_fb=r.pitch_type == primary,
                            game_pk=int(r.game_pk), game_date=str(r.game_date)[:10],
                            at_bat_number=int(r.at_bat_number), pitch_number=int(r.pitch_number), stand=r.stand,
                            release_speed=round(float(r.release_speed), 1), pfx_x_in=round(float(r.pfx_x) * 12, 1),
                            pfx_z_in=round(float(r.pfx_z) * 12, 1)))
    return pd.DataFrame(out, columns=[c for c in MANIFEST_COLS if c not in ("play_id", "source_url", "path",
                                                                            "release_sec")])


def select_consistency(df: pd.DataFrame, pitcher_ids: dict[int, str], pitch_type: str | None = None,
                       n: int = 3) -> pd.DataFrame:
    """n pitches of ONE pitch type spread across the season, for a same-pitch consistency overlay.

    The season is cut into n date windows (early / middle / late); in each window this takes his most
    typical pitch of that type. KC home games are preferred so the Kauffman camera is the same, and so is
    the batter side of the first pick. Rows get set = "same_<PT>" so they are kept apart from the
    one-of-each-pitch picks.
    """
    out = []
    for pid, name in pitcher_ids.items():
        p = df[(df["pitcher"] == pid) & df["is_relief"]] if "is_relief" in df else df[df["pitcher"] == pid]
        if p.empty:
            print("no pitches for", name)
            continue
        pt = pitch_type if pitch_type not in (None, "FB") else pitch_types(p)[0]
        season = p[p["pitch_type"] == pt].dropna(subset=SHAPE_COLS)
        if len(season) < n:
            print(f"{name}: only {len(season)} {pt} pitches; skipping")
            continue
        sd = season[SHAPE_COLS].std().replace(0, np.nan).fillna(1.0)
        dist = (((season[SHAPE_COLS] - season[SHAPE_COLS].mean()) / sd) ** 2).sum(axis=1) ** 0.5
        if "home_team" in season:
            dist = dist + np.where(season["home_team"] == "KC", 0.0, 1.5)
        dates = pd.to_datetime(season["game_date"])
        windows = pd.qcut(dates.rank(method="first"), n, labels=False)
        stand = None
        for w in range(n):
            d = dist[windows == w]
            if stand is not None:
                d = d + np.where(season.loc[d.index, "stand"] == stand, 0.0, 1.0)
            r = season.loc[d.idxmin()]
            stand = stand or r["stand"]
            out.append(dict(pitcher=pid, name=name, pitch_type=pt, is_primary_fb=PITCH_GROUPS.get(pt) == "FB",
                            game_pk=int(r.game_pk), game_date=str(r.game_date)[:10],
                            at_bat_number=int(r.at_bat_number), pitch_number=int(r.pitch_number), stand=r.stand,
                            release_speed=round(float(r.release_speed), 1), pfx_x_in=round(float(r.pfx_x) * 12, 1),
                            pfx_z_in=round(float(r.pfx_z) * 12, 1), set=f"same_{pt}"))
    return pd.DataFrame(out, columns=[c for c in MANIFEST_COLS if c not in ("play_id", "source_url", "path",
                                                                            "release_sec")])


class Blocked(Exception):
    """The server refused a scripted download (403). Save that clip from a browser instead (--file)."""


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 429):
            raise Blocked(f"{exc.code} from {url}") from exc
        raise


def find_play_id(feed: dict, at_bat_number: int, pitch_number: int) -> str | None:
    """Statcast at_bat_number is 1-based; the feed's atBatIndex is 0-based."""
    for play in feed.get("liveData", {}).get("plays", {}).get("allPlays", []):
        if play.get("about", {}).get("atBatIndex") != at_bat_number - 1:
            continue
        for ev in play.get("playEvents", []):
            if ev.get("isPitch") and ev.get("pitchNumber") == pitch_number:
                return ev.get("playId")
    return None


MP4_RE = re.compile(r"https?://[^\"'\s<>]+?\.mp4")


def find_mp4(html: str) -> str | None:
    """First mp4 link on a Savant sporty-videos page or an mlb.com video page."""
    html = html.replace("\\u002F", "/").replace("\\/", "/")
    links = MP4_RE.findall(html)
    return links[0] if links else None


def download(url: str, path: Path) -> bool:
    if path.exists():
        return True
    page_or_file = get(url)
    if url.lower().split("?")[0].endswith(".mp4"):
        data = page_or_file
    else:
        mp4 = find_mp4(page_or_file.decode("utf-8", "ignore"))
        if not mp4:
            print("  no mp4 link found on", url)
            return False
        data = get(mp4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def merge_manifest(new: pd.DataFrame) -> pd.DataFrame:
    """Keep earlier rows (and any release_sec you typed in); new rows replace same pitcher x type x path."""
    if MANIFEST.exists():
        old = pd.read_csv(MANIFEST)
        key = ["pitcher", "pitch_type", "path"]
        keep_sec = old.set_index(key)["release_sec"]
        new = new.copy()
        idx = pd.MultiIndex.from_frame(new[key])
        new["release_sec"] = new["release_sec"].fillna(pd.Series(keep_sec.reindex(idx).values, index=new.index))
        old = old[~old.set_index(key).index.isin(idx)]
        new = pd.concat([old, new], ignore_index=True)
    return new.reindex(columns=MANIFEST_COLS)


def fetch_selected(sel: pd.DataFrame) -> pd.DataFrame:
    sel = sel.copy()
    for c in ("play_id", "source_url", "path"):
        sel[c] = None
    sel["release_sec"] = np.nan
    feeds: dict[int, dict] = {}
    blocked: list[tuple] = []
    for i, r in sel.iterrows():
        path = CLIPS_DIR / slug(r["name"]) / f"{r.pitch_type}_{r.game_pk}_{r.at_bat_number}_{r.pitch_number}.mp4"
        sel.at[i, "path"] = str(path.relative_to(ROOT)).replace("\\", "/")
        try:
            if r.game_pk not in feeds:
                feeds[r.game_pk] = json.loads(get(FEED_URL.format(game_pk=r.game_pk)))
            play_id = find_play_id(feeds[r.game_pk], r.at_bat_number, r.pitch_number)
            if not play_id:
                print("  no playId:", r["name"], r.pitch_type, r.game_pk)
                continue
            url = SAVANT_VIDEO_URL.format(play_id=play_id)
            sel.at[i, "play_id"], sel.at[i, "source_url"] = play_id, url
            if download(url, path):
                print("saved", path.relative_to(ROOT))
        except Blocked as exc:
            blocked.append((r["name"], r.pitch_type, sel.at[i, "source_url"], r.game_date, r.at_bat_number,
                            r.pitch_number))
            print("blocked", r["name"], r.pitch_type, exc)
        except Exception as exc:  # keep going; report the misses
            print("failed", r["name"], r.pitch_type, exc)
    if blocked:
        write_browser_list(blocked)
    return sel


def write_browser_list(blocked: list[tuple]) -> None:
    """For clips MLB refused to a script: which pitch to find in a browser and the command to add it."""
    lines = ["MLB refused these downloads (403 Forbidden). Get each clip in your browser instead:",
             "open the link (or find the pitch in Film Room), save the video, then run the --file command.", ""]
    for name, pt, url, date, ab, pn in blocked:
        lines += [f"{name}  {pt}  {date}  at-bat {ab}, pitch {pn}",
                  f"  open: {url or 'Savant link not found (feed blocked): search this pitch on Film Room'}",
                  f'  then: python -m src.fetch_clips --file "PATH_TO_SAVED.mp4" --pitcher "{name}" --pitch-type {pt}',
                  ""]
    OPEN_IN_BROWSER.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{len(blocked)} clip(s) blocked. What to open and the commands: {OPEN_IN_BROWSER.relative_to(ROOT)}")
    print("Easiest: python -m src.collect_clips  (opens each link, you save it, it files and names the clip)")


def add_file(src: Path, name: str, pitch_type: str, pitcher_id: int | None) -> pd.DataFrame:
    """A clip you saved from a browser: copy it into outputs/clips and add it to the manifest."""
    if not src.exists():
        raise SystemExit(f"file not found: {src}")
    path = CLIPS_DIR / slug(name) / f"{pitch_type}_{slug(src.stem)[:60]}{src.suffix.lower() or '.mp4'}"
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, path)
    print("added", path.relative_to(ROOT))
    return pd.DataFrame([dict(pitcher=pitcher_id, name=name, pitch_type=pitch_type,
                              is_primary_fb=PITCH_GROUPS.get(pitch_type) == "FB", source_url=str(src),
                              path=str(path.relative_to(ROOT)).replace("\\", "/"), release_sec=np.nan)])


def add_manual(url: str, name: str, pitch_type: str, pitcher_id: int | None) -> pd.DataFrame:
    tail = slug(url.rstrip("/").split("/")[-1].split("?")[0])[:60] or "clip"
    path = CLIPS_DIR / slug(name) / f"{pitch_type}_{tail}.mp4"
    try:
        ok = download(url, path)
    except Blocked as exc:
        print("blocked:", exc, "- save it from your browser and use --file")
        ok = False
    print("saved" if ok else "failed", path.relative_to(ROOT))
    return pd.DataFrame([dict(pitcher=pitcher_id, name=name, pitch_type=pitch_type,
                              is_primary_fb=PITCH_GROUPS.get(pitch_type) == "FB", source_url=url,
                              path=str(path.relative_to(ROOT)).replace("\\", "/"), release_sec=np.nan)])


def default_pitchers() -> dict[int, str]:
    leak = pd.read_csv(OUT_TABLES / "leak_map.csv")
    kc = leak[leak["qualified"]]
    return dict(zip(kc["pitcher"].astype(int), kc["reliever"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pitchers", nargs="*", help='names as "Last, First" (default: qualified KC relievers)')
    ap.add_argument("--same", nargs="?", const="FB", metavar="PT",
                    help="consistency set: N pitches of one type across the season (default: his primary FB)")
    ap.add_argument("--n", type=int, default=3, help="with --same: how many pitches (early / mid / late)")
    ap.add_argument("--dry-run", action="store_true", help="pick pitches and print them, no downloads")
    ap.add_argument("--url", help="add one clip by hand from a Film Room / mlb.com / Savant / .mp4 link")
    ap.add_argument("--file", type=Path, help="add a clip you saved from a browser (use when downloads get 403)")
    ap.add_argument("--pitcher", help='with --url: pitcher name, "Last, First"')
    ap.add_argument("--pitcher-id", type=int, help="with --url: MLBAM id (optional)")
    ap.add_argument("--pitch-type", help="with --url: Statcast pitch type, e.g. FF or SL")
    a = ap.parse_args(argv)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    if a.file:
        if not (a.pitcher and a.pitch_type):
            ap.error("--file needs --pitcher and --pitch-type")
        merge_manifest(add_file(a.file, a.pitcher, a.pitch_type.upper(), a.pitcher_id)).to_csv(MANIFEST, index=False)
        return 0
    if a.url:
        if not (a.pitcher and a.pitch_type):
            ap.error("--url needs --pitcher and --pitch-type")
        merge_manifest(add_manual(a.url, a.pitcher, a.pitch_type.upper(), a.pitcher_id)).to_csv(MANIFEST, index=False)
        return 0

    pool = default_pitchers()
    if a.pitchers:
        wanted = set(a.pitchers)
        names = pd.read_csv(OUT_TABLES / "execution_by_reliever.csv")[["pitcher", "name"]].drop_duplicates()
        pool = {int(r.pitcher): r.name for r in names.itertuples() if r.name in wanted}
        missing = wanted - set(pool.values())
        if missing:
            print("not found in execution_by_reliever.csv:", ", ".join(sorted(missing)))
    df = pd.read_parquet(PITCHES_PARQUET, columns=["game_pk", "game_date", "at_bat_number", "pitch_number",
                                                   "pitcher", "pitch_type", "stand", "is_relief", "home_team", *SHAPE_COLS])
    sel = select_consistency(df, pool, a.same.upper(), a.n) if a.same else select_clips(df, pool)
    print(sel.to_string(index=False))
    if a.dry_run:
        return 0
    merge_manifest(fetch_selected(sel)).to_csv(MANIFEST, index=False)
    print("manifest:", MANIFEST.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
