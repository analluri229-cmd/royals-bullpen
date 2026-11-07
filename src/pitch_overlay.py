"""Jomboy-style pitch overlay videos: one pitch type's delivery laid semi-transparently over the fastball.

Takes the clips from src.fetch_clips (outputs/clips/clips_manifest.csv), lines them up on the release
frame, and blends them so both deliveries stay visible. If the arm, body and release look like one
pitcher, the pitch is well hidden; where the two images split early, the delivery tips the pitch.

Alignment: put each clip's release time (seconds into the clip) in the manifest's release_sec column.
Run --sheet first to get a contact sheet of numbered frames for picking it. When a layer has no
release_sec, it is aligned to the base clip by matching their motion over time (same game, same
camera, so the deliveries move the same way). When the base has none either, the release is guessed
as the peak of motion before the first camera cut, and the run says so: check it on the sheet.

Output (no audio track):
  outputs/overlays/<pitcher_slug>_<BASE>_vs_<LAYERS>.mp4   full speed, then slow motion
  outputs/overlays/<pitcher_slug>_<BASE>_vs_<LAYERS>.png   still at release and just after

Needs ffmpeg: uses the one on PATH, else the copy bundled with `pip install imageio-ffmpeg`.

Usage:
  python -m src.pitch_overlay --list
  python -m src.pitch_overlay --pitcher "Erceg, Lucas" --sheet          # frames to pick release_sec
  python -m src.pitch_overlay --pitcher "Erceg, Lucas"                  # FB + every other pitch
  python -m src.pitch_overlay --pitcher "Erceg, Lucas" --layers SL --opacity 0.5 --speeds 1 0.35
  python -m src.pitch_overlay --pitcher "Erceg, Lucas" --same FF      # 2-4 fastballs from different dates
  python -m src.pitch_overlay --pitcher "Erceg, Lucas" --focus 0.05 0.35 0.55 0.95   # blur all but the pitcher
  python -m src.pitch_overlay --base a.mp4 1.84 --layer b.mp4 2.10 --labels FF SL --out x.mp4
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import ROOT

MANIFEST = ROOT / "outputs" / "clips" / "clips_manifest.csv"
OUT_DIR = ROOT / "outputs" / "overlays"
W, H, FPS = 1280, 720, 60
MOTION_W, MOTION_H, MOTION_FPS = 160, 90, 30
KC_BLUE = "#004687"
# for layers of the SAME pitch type (consistency overlays), where Savant colors would all match
SAME_COLORS = ["#D22D49", "#00D1ED", "#EEE716", "#1DBE3A", "#6236CD", "#FE9D00"]
SAVANT_COLORS = {"FF": "#D22D49", "SI": "#FE9D00", "FC": "#933F2C", "SL": "#EEE716", "ST": "#DDB33A",
                 "SV": "#93AFD4", "CU": "#00D1ED", "KC": "#6236CD", "CH": "#1DBE3A", "FS": "#3BACAC",
                 "FO": "#55CCAB"}
PITCH_NAMES = {"FF": "four-seam", "SI": "sinker", "FC": "cutter", "SL": "slider", "ST": "sweeper",
               "SV": "slurve", "CU": "curveball", "KC": "knuckle curve", "CH": "changeup", "FS": "splitter",
               "FO": "forkball"}


@dataclass
class Clip:
    path: Path
    label: str          # pitch type, e.g. "SL"
    release: float | None
    note: str = ""      # e.g. "88.1 mph"


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise SystemExit("ffmpeg not found: pip install imageio-ffmpeg (or install ffmpeg)") from exc


def run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + res.stderr[-2000:])


# ---------- alignment ----------

def motion_curve(path: Path) -> np.ndarray:
    """Mean absolute grayscale change between consecutive frames, sampled at MOTION_FPS."""
    cmd = [ffmpeg_exe(), "-v", "error", "-i", str(path), "-an", "-vf",
           f"fps={MOTION_FPS},scale={MOTION_W}:{MOTION_H},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, MOTION_H, MOTION_W).astype(np.float32)
    if len(frames) < 2:
        return np.zeros(1)
    return np.concatenate([[0.0], np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))])


def first_cut(curve: np.ndarray, factor: float = 6.0) -> int:
    """Index of the first camera cut: a jump far above the clip's typical motion (len if none)."""
    base = np.median(curve[1:]) + 1e-6
    hits = np.where(curve > max(factor * base, 12.0))[0]
    hits = hits[hits > MOTION_FPS // 2]  # ignore a cut in the first half second (clip start)
    return int(hits[0]) if len(hits) else len(curve)


def guess_release(curve: np.ndarray) -> float:
    """Release guess: peak of smoothed motion before the first cut, in seconds."""
    end = first_cut(curve)
    seg = np.convolve(curve[:end], np.ones(5) / 5, mode="same")
    return float(np.argmax(seg)) / MOTION_FPS


def align_offset(base: np.ndarray, layer: np.ndarray, base_release: float, window: float = 1.0,
                 max_shift: float = 4.0) -> float:
    """Layer release time that best matches the base: shift that maximizes correlation of motion curves
    over a window around the base release."""
    base, layer = base.copy(), layer.copy()
    base[first_cut(base):] = 0.0  # a camera cut is not part of the delivery
    layer[first_cut(layer):] = 0.0
    b0 = max(0, int((base_release - window) * MOTION_FPS))
    b1 = min(len(base), int((base_release + window) * MOTION_FPS))
    seg = base[b0:b1]
    seg = (seg - seg.mean()) / (seg.std() + 1e-6)
    best, best_t = -np.inf, base_release
    for start in range(0, max(1, len(layer) - len(seg) + 1)):
        if abs(start - b0) > max_shift * MOTION_FPS:
            continue
        cand = layer[start:start + len(seg)]
        if len(cand) < len(seg):
            break
        cand = (cand - cand.mean()) / (cand.std() + 1e-6)
        score = float(np.dot(seg, cand))
        if score > best:
            best, best_t = score, base_release + (start - b0) / MOTION_FPS
    return round(best_t, 3)


def resolve_releases(clips: list[Clip]) -> list[str]:
    """Fill in missing release times. Returns notes on what was guessed."""
    notes = []
    base = clips[0]
    curves = {}
    if base.release is None:
        curves[0] = motion_curve(base.path)
        base.release = round(guess_release(curves[0]), 3)
        notes.append(f"{base.label}: release guessed at {base.release:.2f}s from motion; check with --sheet")
    for i, c in enumerate(clips[1:], start=1):
        if c.release is None:
            curves.setdefault(0, motion_curve(base.path))
            c.release = align_offset(curves[0], motion_curve(c.path), base.release)
            notes.append(f"{c.label}: aligned to {base.label} by motion at {c.release:.2f}s")
    return notes


# ---------- labels ----------

def label_png(path: Path, title: str, clips: list[Clip], alphas: list[float], credit: str) -> Path:
    """Transparent 1280x720 PNG with the title, a pitch legend and the credit line."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    rows = len(clips)
    box_h = 56 + 30 * rows
    ax.add_patch(FancyBboxPatch((18, 18), 560, box_h, boxstyle="round,pad=0,rounding_size=10",
                                facecolor=KC_BLUE, alpha=0.88, edgecolor="none"))
    ax.text(34, 46, title, color="white", fontsize=17, fontweight="bold", va="center")
    same = len({c.label for c in clips}) < len(clips)
    for i, (c, a) in enumerate(zip(clips, alphas)):
        y = 84 + 30 * i
        col = SAME_COLORS[i % len(SAME_COLORS)] if same else SAVANT_COLORS.get(c.label, "#FFFFFF")
        ax.add_patch(FancyBboxPatch((34, y - 10), 20, 20, boxstyle="round,pad=0,rounding_size=3",
                                    facecolor=col, edgecolor="white", lw=1))
        layer = "base layer" if i == 0 else f"{a:.0%} opacity on top"
        name = PITCH_NAMES.get(c.label, c.label)
        ax.text(66, y, f"{c.label} {name}  {c.note}".rstrip() + f"   ({layer})", color="white", fontsize=13,
                va="center")
    ax.text(W - 18, H - 16, credit, color="white", fontsize=10, ha="right", va="bottom",
            bbox=dict(facecolor="black", alpha=0.45, edgecolor="none", pad=4))
    fig.savefig(path, dpi=100, transparent=True)
    plt.close(fig)
    return path


# ---------- render ----------

def layer_alphas(n_layers: int, opacity: float | None) -> list[float]:
    """Alpha for each layer drawn on the base. Default: equal visibility for every clip
    (1/2 for one layer; 1/2 then 1/3 for two, ...). A fixed opacity applies to every layer."""
    return [opacity if opacity is not None else 1.0 / (k + 2) for k in range(n_layers)]


def focus_box(focus: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) as fractions of the frame -> even-pixel (x, y, w, h) at W x H."""
    l, t, r, b = (min(max(v, 0.0), 1.0) for v in focus)
    if r <= l or b <= t:
        raise SystemExit("--focus needs LEFT < RIGHT and TOP < BOTTOM (fractions 0-1)")
    even = lambda v: int(round(v)) // 2 * 2  # noqa: E731
    return even(l * W), even(t * H), max(2, even((r - l) * W)), max(2, even((b - t) * H))


def build_filter(clips: list[Clip], alphas: list[float], pre: float, post: float, speeds: list[float],
                 focus: tuple[float, float, float, float] | None = None, blur: int = 18) -> str:
    """Filtergraph: trim each clip to [release - pre, release + post], blend layers onto the base,
    optionally blur everything outside the focus box (crowd, dugout, scoreboard), put the label PNG
    on top, then play the result once per speed in order."""
    n = len(clips)
    parts = []
    for i, c in enumerate(clips):
        chain = (f"[{i}:v]trim=start={max(0.0, c.release - pre):.3f}:duration={pre + post:.3f},"
                 f"setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease,"
                 f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1")
        if i > 0:
            chain += f",format=yuva420p,colorchannelmixer=aa={alphas[i - 1]:.3f}"
        parts.append(chain + f"[c{i}]")
    cur = "c0"
    for i in range(1, n):
        parts.append(f"[{cur}][c{i}]overlay=shortest=1:format=auto[m{i}]")
        cur = f"m{i}"
    if focus is not None:
        x, y, w, h = focus_box(focus)
        parts.append(f"[{cur}]split=2[fa][fb]")
        parts.append(f"[fa]boxblur={blur}:2[fbl]")
        parts.append(f"[fb]crop={w}:{h}:{x}:{y}[fsh]")
        parts.append(f"[fbl][fsh]overlay={x}:{y}[foc]")
        cur = "foc"
    parts.append(f"[{cur}][{n}:v]overlay=format=auto:shortest=1,format=yuv420p[ov]")
    if len(speeds) == 1:
        parts.append(f"[ov]setpts=PTS/{speeds[0]}[out]")
    else:
        splits = "".join(f"[s{k}]" for k in range(len(speeds)))
        parts.append(f"[ov]split={len(speeds)}{splits}")
        for k, sp in enumerate(speeds):
            parts.append(f"[s{k}]setpts=(PTS-STARTPTS)/{sp},fps={FPS}[p{k}]")
        ins = "".join(f"[p{k}]" for k in range(len(speeds)))
        parts.append(f"{ins}concat=n={len(speeds)}:v=1:a=0[out]")
    return ";".join(parts)


def render(clips: list[Clip], out: Path, title: str, opacity: float | None = None, pre: float = 1.4,
           post: float = 0.9, speeds: tuple[float, ...] = (1.0, 0.35),
           credit: str = "Video: MLB / Baseball Savant. Aligned on release.",
           focus: tuple[float, float, float, float] | None = None, blur: int = 18) -> tuple[Path, Path, list[str]]:
    notes = resolve_releases(clips)
    lead = min(c.release for c in clips)
    if lead < pre:  # every clip must keep the same lead-in, or the release frames drift apart
        notes.append(f"lead-in cut to {lead:.2f}s (a clip's release is that close to its start)")
        pre = lead
    alphas = layer_alphas(len(clips) - 1, opacity)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        png = label_png(Path(tmp) / "labels.png", title, clips, [1.0] + alphas, credit)
        cmd = [ffmpeg_exe(), "-y", "-v", "error"]
        for c in clips:
            cmd += ["-i", str(c.path)]
        cmd += ["-loop", "1", "-i", str(png), "-filter_complex",
                build_filter(clips, alphas, pre, post, list(speeds), focus, blur), "-map", "[out]", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
                "-movflags", "+faststart", str(out)]
        run(cmd)
    still = out.with_suffix(".png")
    stills(out, still, pre)
    return out, still, notes


def stills(video: Path, out: Path, pre: float, after: float = 0.25) -> Path:
    """Side by side: the frame at release and `after` seconds later (first, full-speed pass)."""
    vf = (f"select='eq(n\\,{round(pre * FPS)})+eq(n\\,{round((pre + after) * FPS)})',"
          f"scale={W // 2}:-2,tile=2x1")
    run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(video), "-vf", vf, "-frames:v", "1", "-update", "1",
         str(out)])
    return out


def grid_frame(path: Path, out: Path, at: float) -> Path:
    """One frame (at `at` seconds, scaled to the output size) with a 10% grid, for choosing --focus."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cmd = [ffmpeg_exe(), "-v", "error", "-ss", f"{max(at, 0):.3f}", "-i", str(path), "-an", "-frames:v", "1", "-vf",
           f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    img = np.frombuffer(raw, np.uint8)[: W * H * 3].reshape(H, W, 3)
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img, extent=(0, 1, 1, 0))
    for k in range(1, 10):
        ax.axvline(k / 10, color="yellow", lw=0.8, alpha=0.8)
        ax.axhline(k / 10, color="yellow", lw=0.8, alpha=0.8)
        ax.text(k / 10, 0.015, f"{k / 10:.1f}", color="yellow", ha="center", va="top", fontsize=11, fontweight="bold")
        ax.text(0.005, k / 10, f"{k / 10:.1f}", color="yellow", ha="left", va="center", fontsize=11, fontweight="bold")
    ax.set_xlim(0, 1)
    ax.set_ylim(1, 0)
    ax.axis("off")
    ax.text(0.5, 0.97, "--focus LEFT TOP RIGHT BOTTOM: keep the pitcher (and catcher) sharp, blur the rest",
            color="white", ha="center", fontsize=13, bbox=dict(facecolor="black", alpha=0.6, edgecolor="none"))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


def clip_duration(path: Path) -> float:
    """Clip length in seconds, read from ffmpeg's header line (works with the imageio-ffmpeg binary)."""
    import re
    res = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def contact_sheet(path: Path, out: Path, start: float = 0.0, step: float = 1 / 15, cols: int = 6,
                  rows: int = 8) -> Path:
    """Grid of frames with their time in seconds burned in (via the frame number), for picking release_sec."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = cols * rows
    tw, th = 320, 180
    cmd = [ffmpeg_exe(), "-v", "error", "-ss", f"{start:.3f}", "-i", str(path), "-an", "-vf",
           f"fps={1 / step:.4f},scale={tw}:{th}", "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, th, tw, 3)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.2, rows * 1.95))
    for k, ax in enumerate(np.ravel(axes)):
        ax.axis("off")
        if k < len(frames):
            ax.imshow(frames[k])
            ax.set_title(f"{start + k * step:.2f}s", fontsize=9, color=KC_BLUE, fontweight="bold")
    fig.suptitle(f"{path.name}: pick the frame where the ball leaves the hand -> release_sec", fontsize=11,
                 x=0.01, ha="left")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=100)
    plt.close(fig)
    return out


# ---------- manifest helpers ----------

def slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(text).lower()).strip("_")


def short(name: str) -> str:
    return str(name).split(",")[0]


def clips_for(man: pd.DataFrame, pitcher: str, base: str | None, layers: list[str] | None) -> list[Clip]:
    m = man[man["name"] == pitcher]
    if m.empty:
        raise SystemExit(f"{pitcher!r} not in {MANIFEST.relative_to(ROOT)}; run python -m src.fetch_clips first")
    m = m[m["path"].map(lambda p: (ROOT / str(p)).exists())]
    if base is None:
        fb = m[m["is_primary_fb"].astype(str).str.lower() == "true"]
        base = (fb if not fb.empty else m).iloc[0]["pitch_type"]
    order = [base] + (layers or [t for t in m["pitch_type"] if t != base])
    clips = []
    for t in dict.fromkeys(order):
        row = m[m["pitch_type"] == t]
        if row.empty:
            print(f"no downloaded {t} clip for {pitcher}; skipping")
            continue
        r = row.iloc[-1]
        rel = None if pd.isna(r.get("release_sec")) else float(r["release_sec"])
        note = f"{r['release_speed']:.1f} mph" if pd.notna(r.get("release_speed")) else ""
        clips.append(Clip(ROOT / str(r["path"]), t, rel, note))
    if len(clips) < 2:
        raise SystemExit("need a base clip and at least one layer")
    return clips


def same_pitch_clips(man: pd.DataFrame, pitcher: str, pitch_type: str | None, limit: int = 4) -> list[Clip]:
    """Every downloaded clip of one pitch type for this pitcher, oldest first, labeled by date.
    Prefers the fetch_clips --same set; falls back to any clips of that type."""
    m = man[(man["name"] == pitcher)]
    m = m[m["path"].map(lambda p: (ROOT / str(p)).exists())]
    if pitch_type is None:
        fb = m[m["is_primary_fb"].astype(str).str.lower() == "true"]
        pitch_type = (fb if not fb.empty else m).iloc[0]["pitch_type"]
    m = m[m["pitch_type"] == pitch_type]
    if "set" in m and (m["set"] == f"same_{pitch_type}").sum() >= 2:
        m = m[m["set"] == f"same_{pitch_type}"]
    m = m.sort_values("game_date", na_position="last").head(limit)
    clips = []
    for r in m.itertuples():
        bits = [pd.to_datetime(r.game_date).strftime("%b %d").replace(" 0", " ") if pd.notna(r.game_date) else "",
                f"{r.release_speed:.1f} mph" if pd.notna(r.release_speed) else ""]
        rel = None if pd.isna(r.release_sec) else float(r.release_sec)
        clips.append(Clip(ROOT / str(r.path), pitch_type, rel, "  ".join(b for b in bits if b)))
    if len(clips) < 2:
        raise SystemExit(f"need 2+ downloaded {pitch_type} clips for {pitcher}: "
                         f"python -m src.fetch_clips --pitchers \"{pitcher}\" --same {pitch_type}")
    return clips


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show the clips in the manifest")
    ap.add_argument("--pitcher", help='name as in the manifest, "Last, First"')
    ap.add_argument("--base", help="base pitch type (default: his primary fastball)")
    ap.add_argument("--layers", nargs="*", help="pitch types to put on top (default: all others)")
    ap.add_argument("--opacity", type=float, help="alpha for every layer (default: equal mix, 0.5 for one)")
    ap.add_argument("--pre", type=float, default=1.4, help="seconds kept before release")
    ap.add_argument("--post", type=float, default=0.9, help="seconds kept after release")
    ap.add_argument("--speeds", nargs="+", type=float, default=[1.0, 0.35], help="play once at each speed")
    ap.add_argument("--same", nargs="?", const="", metavar="PT",
                    help="consistency overlay: several clips of ONE pitch type (default: his primary FB)")
    ap.add_argument("--focus", nargs=4, type=float, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                    help="keep this box sharp and blur the rest; fractions of the frame (see the --sheet grid)")
    ap.add_argument("--blur", type=int, default=18, help="with --focus: blur strength (default 18)")
    ap.add_argument("--sheet", action="store_true", help="write contact sheets for picking release_sec")
    ap.add_argument("--clip", nargs=2, action="append", metavar=("PATH", "RELEASE_SEC"),
                    help="manual mode: first --clip is the base, then layers; RELEASE_SEC may be 'auto'")
    ap.add_argument("--labels", nargs="*", help="manual mode: pitch type for each --clip")
    ap.add_argument("--title", help="title on the video")
    ap.add_argument("--out", help="manual mode: output .mp4")
    a = ap.parse_args(argv)

    if a.clip:
        labels = a.labels or [f"P{i}" for i in range(len(a.clip))]
        clips = [Clip(Path(p), lab, None if s == "auto" else float(s)) for (p, s), lab in zip(a.clip, labels)]
        out = Path(a.out or OUT_DIR / "overlay.mp4")
        title = a.title or f"{clips[0].label} vs " + " + ".join(c.label for c in clips[1:])
    else:
        man = pd.read_csv(MANIFEST)
        if a.list or not a.pitcher:
            print(man[["name", "pitch_type", "game_date", "release_speed", "release_sec", "path"]].to_string(index=False))
            return 0
        clips = (same_pitch_clips(man, a.pitcher, a.same.upper() or None) if a.same is not None
                 else clips_for(man, a.pitcher, a.base, a.layers))
        if a.sheet:
            for c in clips:
                # long clips (replays, cut-aways) get an overview of the whole clip plus a close-up
                # around the guessed release, so the release can be found in a 5 s or a 13 s clip
                dur = clip_duration(c.path)
                guess = c.release if c.release is not None else guess_release(motion_curve(c.path))
                over = contact_sheet(c.path, OUT_DIR / "sheets" / f"{c.path.stem}_overview.png",
                                     step=max(dur / 48, 1 / 15) if dur else 0.25)
                p = contact_sheet(c.path, OUT_DIR / "sheets" / f"{c.path.stem}.png", start=max(0.0, guess - 1.6))
                print(f"{c.path.name}: {dur:.1f}s long, release guess {guess:.2f}s")
                print("  overview:", over.relative_to(ROOT))
                print("  close-up:", p.relative_to(ROOT))
            g = grid_frame(clips[0].path, OUT_DIR / "sheets" / f"{clips[0].path.stem}_grid.png",
                           clips[0].release if clips[0].release is not None else 1.0)
            print("grid for --focus:", g.relative_to(ROOT))
            print(f"Put each release time in release_sec in {MANIFEST.relative_to(ROOT)}, then rerun without --sheet.")
            return 0
        tag = (f"{clips[0].label}_consistency" if a.same is not None
               else f"{clips[0].label}_vs_{'_'.join(c.label for c in clips[1:])}")
        out = OUT_DIR / f"{slug(a.pitcher)}_{tag}.mp4"
        title = a.title or (f"{short(a.pitcher)}: {PITCH_NAMES.get(clips[0].label, clips[0].label)} "
                            f"consistency, {len(clips)} outings" if a.same is not None else
                            f"{short(a.pitcher)}: {PITCH_NAMES.get(clips[0].label, clips[0].label)} vs "
                            + " + ".join(PITCH_NAMES.get(c.label, c.label) for c in clips[1:]))
    video, still, notes = render(clips, out, title, a.opacity, a.pre, a.post, tuple(a.speeds),
                                 focus=tuple(a.focus) if a.focus else None, blur=a.blur)
    for n in notes:
        print("note:", n)
    print("releases:", ", ".join(f"{c.label} {c.release:.2f}s" for c in clips))
    print("saved", video)
    print("saved", still)
    return 0


if __name__ == "__main__":
    sys.exit(main())
