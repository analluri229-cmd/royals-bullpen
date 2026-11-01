"""Step 8: slide figures (300 dpi PNG, outputs/figures). Royals blue for KC, gray for league.

Every figure is drawn from a table in outputs/tables, so each number traces back.

  slide1_bullpen_ranks.png        K-BB%, xFIP and WAR for the 30 bullpens (FanGraphs)
  slide2_stuff_vs_execution.png   Stuff vs Execution score, all qualified relievers
  slide2_leak_heatmap.png         KC relievers x Stuff/Execution percentiles
  slide3_movement.png             HB vs IVB for the top Execution-fix arms over the league cloud
  slide3_tunnel.png               KC pitch-pair tunnel distance at 23.8 ft vs league median
  slide3_sequence_heatmap.png     KC previous pitch group x next pitch group, Whiff% on the 2nd pitch
  slide3_often_vs_well.png        Step 5A How often vs How well percentiles (delivery, tunneling)
  slide5_targets.png              Replace/re-sign decisions with top free-agent fits

Usage:  python -m src.figures
"""
from __future__ import annotations

import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import OUT_TABLES, ROOT  # noqa: E402
from src.leak_map import ordinal  # noqa: E402
from src.stuff import PITCH_GROUPS  # noqa: E402

KC_BLUE = "#004687"
GRAY = "#B8BCC2"
DARK = "#3A3F45"
DPI = 300
OUT_FIGS = ROOT / "outputs" / "figures"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 11,
                     "axes.edgecolor": DARK, "axes.labelcolor": DARK, "xtick.color": DARK,
                     "ytick.color": DARK})


def short(name: str) -> str:
    """'Lynch IV, Daniel' -> 'Lynch IV'."""
    return str(name).split(",")[0]


def save(fig, name: str):
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    path = OUT_FIGS / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def bar_colors(index, team="KCR"):
    return [KC_BLUE if t == team else GRAY for t in index]


# ---------------------------------------------------------------- slide 1

def slide1_ranks(ranks: pd.DataFrame, kc_team: str):
    panels = [("K-BB%", "K-BB% (higher is better)", False), ("xFIP", "xFIP (lower is better)", True),
              ("WAR", "Reliever WAR (higher is better)", False)]
    fig, axes = plt.subplots(1, 3, figsize=(12, 6.2))
    for ax, (col, title, asc) in zip(axes, panels):
        d = ranks.sort_values(col, ascending=not asc)  # best at top
        ax.barh(d["Team"], d[col], color=bar_colors(d["Team"], kc_team), height=0.72)
        ax.invert_yaxis()
        kc = d[d["Team"] == kc_team].iloc[0]
        ax.set_title(f"{title}\nKC ranks {int(kc[f'{col}_rank'])} of 30", loc="left")
        ax.tick_params(axis="y", labelsize=7)
        for lbl in ax.get_yticklabels():
            if lbl.get_text() == kc_team:
                lbl.set_color(KC_BLUE)
                lbl.set_fontweight("bold")
        lo = d[col].min()
        ax.set_xlim(lo * 0.9 if col != "WAR" else min(0, lo * 1.1), d[col].max() * 1.05)
    fig.suptitle("The Royals bullpen ranks near the bottom of MLB in 2026", x=0.01, ha="left",
                 fontsize=14, fontweight="bold", color=DARK)
    fig.text(0.01, -0.01, "Source: FanGraphs team reliever leaderboard, 2026 regular season "
             "(outputs/tables/team_bullpen_ranks_2026.csv)", fontsize=7, color=DARK)
    fig.tight_layout()
    return save(fig, "slide1_bullpen_ranks.png")


# ---------------------------------------------------------------- slide 2

QUAD_TEXT = {(1, 1): "Keep", (0, 1): "Stuff fix", (1, 0): "Execution fix", (0, 0): "Replace candidate"}


def slide2_scatter(scores: pd.DataFrame, leak: pd.DataFrame):
    lg = scores[scores["qualified"] & scores["group"].ne("KC reliever")]
    kc = leak[leak["qualified"]]
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.scatter(lg["stuff_score"], lg["execution_score"], s=14, color=GRAY, alpha=0.7, lw=0,
               label=f"MLB relievers (n={len(lg)})")
    ax.scatter(kc["stuff_score"], kc["execution_score"], s=60, color=KC_BLUE, zorder=3,
               edgecolor="white", lw=0.8, label=f"Royals relievers (n={len(kc)})")
    for r in kc.itertuples():
        ax.annotate(short(r.reliever), (r.stuff_score, r.execution_score), xytext=(5, 3),
                    textcoords="offset points", fontsize=8, color=KC_BLUE, fontweight="bold")
    ax.axvline(50, color=DARK, lw=0.8, ls="--")
    ax.axhline(50, color=DARK, lw=0.8, ls="--")
    for (sx, ey), txt in QUAD_TEXT.items():
        ax.text(98 if sx else 2, 98 if ey else 48 if sx else 2, txt, ha="right" if sx else "left",
                va="top" if (ey or sx) else "bottom", fontsize=10, color=DARK, alpha=0.75, fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Stuff score (percentile vs qualified relievers)")
    ax.set_ylabel("Execution score (percentile vs qualified relievers)")
    n_hi = (kc["stuff_score"] >= 50).sum()
    n_lo = (kc["execution_score"] < 50).sum()
    ax.set_title(f"Royals arms have the stuff but not the execution: {n_hi} of {len(kc)} above average "
                 f"on Stuff, {n_lo} of {len(kc)} below on Execution", loc="left", fontsize=10)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.93), frameon=False, fontsize=8)
    fig.text(0.01, -0.01, "Stuff = Stuff+ percentile (FB 50%, best secondary 30%, rest 20%). Execution = mean "
             "percentile of Zone%, F-Strike%, 3PS%, Kill%, BB% (inv.), Chase%. Source: leak_map.csv, "
             "scores_all_relievers.csv", fontsize=6.5, color=DARK)
    return save(fig, "slide2_stuff_vs_execution.png")


HEAT_COLS = [("stuff_score", "Stuff\nscore"), ("primary_fb_pctile", "Fastball\nStuff+"),
             ("best_secondary_pctile", "Best 2nd\nStuff+"), ("execution_score", "Execution\nscore"),
             ("zone_pct_good", "Zone%"), ("f_strike_pct_good", "F-Strike%"), ("three_ps_pct_good", "3PS%"),
             ("kill_pct_good", "Kill%"), ("bb_pct_good", "BB%\n(inv.)"), ("chase_pct_good", "Chase%")]


def slide2_heatmap(leak: pd.DataFrame, exe_good: pd.DataFrame, stuff_parts: pd.DataFrame):
    kc = leak[leak["qualified"]].merge(exe_good, on="pitcher", how="left").merge(stuff_parts, on="pitcher",
                                                                                  how="left")
    kc = kc.sort_values("execution_score", ascending=False)
    mat = kc[[c for c, _ in HEAT_COLS]].to_numpy(float)
    fig, ax = plt.subplots(figsize=(10, 6.2))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("rb", ["#B2182B", "#F7F7F7", KC_BLUE])
    im = ax.imshow(mat, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(v - 50) > 32 else DARK)
    ax.set_xticks(range(len(HEAT_COLS)), [lab for _, lab in HEAT_COLS], fontsize=8)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(kc)), [f"{short(n)}  ({q})" for n, q in zip(kc["reliever"], kc["quadrant"])],
                  fontsize=8)
    ax.axvline(3.5, color="white", lw=4)
    ax.spines[:].set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("League percentile (100 = best)")
    ax.set_title("Leak map: where each Royals reliever falls short (percentile vs qualified relievers)",
                 loc="left", pad=36)
    fig.text(0.01, -0.01, "Red = below league average, blue = above. Source: leak_map.csv, "
             "execution_by_reliever.csv, stuff_by_pitch.csv", fontsize=6.5, color=DARK)
    return save(fig, "slide2_leak_heatmap.png")


# ---------------------------------------------------------------- slide 3

GROUP_COLOR = {"FB": "#C8102E", "BRK": "#2E7D32", "OFF": "#F2A900"}


def slide3_movement(stuff: pd.DataFrame, leak: pd.DataFrame, n: int = 4):
    s = stuff[stuff["sample_flag"].fillna("").eq("")]
    fix = leak[leak["qualified"] & leak["quadrant"].eq("Execution fix")].nlargest(n, "stuff_score")
    fig, axes = plt.subplots(1, len(fix), figsize=(4 * len(fix), 4.4), sharex=True, sharey=True)
    axes = np.atleast_1d(axes)
    for ax, r in zip(axes, fix.itertuples()):
        mine = s[s["pitcher"] == r.pitcher]
        hand = mine["throws"].iloc[0]
        lg = s[(s["throws"] == hand) & ~s["group"].eq("KC reliever")]
        ax.scatter(lg["hb"], lg["ivb"], s=5, color=GRAY, alpha=0.35, lw=0)
        for p in mine.itertuples():
            c = GROUP_COLOR.get(p.pitch_group, DARK)
            ax.scatter(p.hb, p.ivb, s=40 + 4 * p.usage_pct, color=c, edgecolor=DARK, lw=0.6, zorder=3)
            sp = "" if pd.isna(p.stuff_plus) else f"  {p.stuff_plus:.0f}"
            ax.annotate(f"{p.pitch_type} {p.velo:.0f}{sp}", (p.hb, p.ivb), xytext=(6, 4),
                        textcoords="offset points", fontsize=7.5, fontweight="bold", color=DARK)
        ax.axhline(0, color=DARK, lw=0.4)
        ax.axvline(0, color=DARK, lw=0.4)
        ax.set_title(f"{short(r.reliever)} ({hand}HP)\nStuff {r.stuff_score:.0f}, Execution {r.execution_score:.0f}",
                     loc="left", fontsize=9.5, color=KC_BLUE)
        ax.set_xlabel("Horizontal break (in, catcher's view)")
    axes[0].set_ylabel("Induced vertical break (in)")
    fig.suptitle("Movement is not the problem: the Execution-fix arms already have league-quality shapes",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=DARK)
    fig.text(0.01, -0.03, "Labels: pitch, velocity (mph), Stuff+. Gray = MLB relievers' pitch averages, same hand "
             "(50+ pitches). Dot size = usage. Source: stuff_by_pitch.csv", fontsize=6.5, color=DARK)
    fig.tight_layout()
    return save(fig, "slide3_movement.png")


def slide3_tunnel(pairs: pd.DataFrame, min_pairs: int = 25):
    g = pairs.groupby(["player_name", "pair"]).agg(n=("tunnel_in", "size"), tunnel=("tunnel_in", "median"),
                                                     league=("league_median_tunnel_in", "median"),
                                                     plate=("plate_in", "median")).reset_index()
    g = g[g["n"] >= min_pairs]
    g["gap"] = g["tunnel"] - g["league"]
    show = pd.concat([g.nsmallest(6, "gap"), g.nlargest(6, "gap")]).drop_duplicates().sort_values("gap")
    fig, ax = plt.subplots(figsize=(8.5, 5.8))
    y = np.arange(len(show))
    ax.hlines(y, show["league"], show["tunnel"], color=GRAY, lw=2)
    ax.scatter(show["league"], y, color=GRAY, s=40, label="League median, same pair and hand", zorder=3)
    ax.scatter(show["tunnel"], y, color=KC_BLUE, s=55, label="Royals pitcher", zorder=4)
    ax.set_yticks(y, [f"{short(n)}  {p}  (n={k})" for n, p, k in zip(show["player_name"], show["pair"], show["n"])],
                  fontsize=8)
    ax.set_xlabel("Distance between back-to-back pitches at 23.8 ft from the plate (inches; smaller = better tunnel)")
    ax.set_title("Best and worst Royals pitch tunnels vs the league", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.text(0.01, -0.02, f"Pairs thrown back to back in the same PA, {min_pairs}+ pairs. "
             "Source: sequence_pairs.csv (Step 5A)", fontsize=6.5, color=DARK)
    return save(fig, "slide3_tunnel.png")


def slide3_sequence_heatmap(summ: pd.DataFrame, kc_ids):
    s = summ[summ["pitcher"].isin(set(kc_ids))].copy()
    s[["prev", "next"]] = s["seq"].str.split("->", expand=True)
    s["prev_g"] = s["prev"].map(PITCH_GROUPS)
    s["next_g"] = s["next"].map(PITCH_GROUPS)
    s = s.dropna(subset=["prev_g", "next_g"])
    agg = s.groupby(["prev_g", "next_g"])[["swings", "whiffs", "n"]].sum()
    agg["whiff"] = 100 * agg["whiffs"] / agg["swings"]
    order = ["FB", "BRK", "OFF"]
    labels = {"FB": "Fastball", "BRK": "Breaking", "OFF": "Offspeed"}
    w = agg["whiff"].unstack().reindex(index=order, columns=order)
    n = agg["n"].unstack().reindex(index=order, columns=order)
    fig, ax = plt.subplots(figsize=(5.8, 4.8))
    from matplotlib.colors import LinearSegmentedColormap
    im = ax.imshow(w.to_numpy(float), cmap=LinearSegmentedColormap.from_list("b", ["#F7F7F7", KC_BLUE]),
                   vmin=0, vmax=max(45, np.nanmax(w.to_numpy(float))))
    for i in range(3):
        for j in range(3):
            v = w.iat[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.0f}%\nn={int(n.iat[i, j])}", ha="center", va="center", fontsize=9,
                        color="white" if v > 30 else DARK)
    ax.set_xticks(range(3), [labels[o] for o in order])
    ax.set_yticks(range(3), [labels[o] for o in order])
    ax.set_xlabel("Next pitch")
    ax.set_ylabel("Previous pitch")
    ax.spines[:].set_visible(False)
    ax.set_title("Royals bullpen: Whiff% on the 2nd pitch\nof each two-pitch sequence", loc="left")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03).set_label("Whiff% (whiffs / swings)")
    fig.text(0.01, -0.02, "Qualified KC relievers, relief pitches. Source: sequence_summary.csv (Step 5)",
             fontsize=6.5, color=DARK)
    return save(fig, "slide3_sequence_heatmap.png")


def slide3_often_vs_well(tri: pd.DataFrame, leak: pd.DataFrame, scores: pd.DataFrame):
    kc = leak[leak["qualified"]][["pitcher", "reliever"]]
    q_ids = set(scores.loc[scores["qualified"], "pitcher"])
    patterns = [("delivery", "Delivery (release consistency)"), ("tunneling", "Tunneling")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharex=True, sharey=True)
    for ax, (pat, title) in zip(axes, patterns):
        t = tri[tri["pattern"] == pat]
        lg = t[t["pitcher_id"].isin(q_ids) & ~t["pitcher_id"].isin(set(kc["pitcher"]))]
        ax.scatter(lg["often"], lg["well"], s=10, color=GRAY, alpha=0.6, lw=0)
        k = t.merge(kc, left_on="pitcher_id", right_on="pitcher")
        ax.scatter(k["often"], k["well"], s=55, color=KC_BLUE, edgecolor="white", zorder=3)
        for r in k.itertuples():
            ax.annotate(short(r.reliever), (r.often, r.well), xytext=(4, 3), textcoords="offset points",
                        fontsize=7.5, color=KC_BLUE, fontweight="bold")
        ax.axvline(50, color=DARK, lw=0.7, ls="--")
        ax.axhline(50, color=DARK, lw=0.7, ls="--")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.set_title(title, loc="left")
        ax.set_xlabel("How often (league percentile)")
    axes[0].set_ylabel("How well (league percentile)")
    fig.suptitle("Sequencing triage: how often each Royals reliever uses a pattern vs how well it works\n"
                 "Top-left = effective but underused (coaching opportunity); bottom-left = low on both (coaching target)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=DARK)
    fig.text(0.01, -0.03, "Delivery: often = share of pitches released within 2 in of the fastball; well = release "
             "gap percentile. Tunneling: often = share of pairs below the league median tunnel distance; well = "
             "whiff and chase lift percentiles. Source: sequencing_triage.csv", fontsize=6.5, color=DARK)
    fig.tight_layout()
    return save(fig, "slide3_often_vs_well.png")


PITCH_COLORS = ["#004687", "#C8102E", "#2E7D32", "#F2A900", "#6A3D9A", "#8C564B"]
ARM_LEN_IN = 30.0  # drawn arm length, for display only


def delivery_overlay(dpitch: pd.DataFrame, dpitcher: pd.DataFrame, names: list[str]):
    """Catcher's-view overlay of each pitch type's release point and arm slot, one panel per pitcher.

    Dots are mean release points (inches), ellipses are 1 SD, and the line is a 30-inch arm drawn
    back from release at that pitch type's mean Statcast arm angle. Pitches that share a slot overlap.
    """
    from matplotlib.patches import Ellipse
    fig, axes = plt.subplots(1, len(names), figsize=(6.2 * len(names), 6.4))
    axes = np.atleast_1d(axes)
    for ax, nm in zip(axes, names):
        d = dpitch[(dpitch["name"] == nm) & (dpitch["n_pitches"] >= 50)].sort_values("n_pitches", ascending=False)
        summ = dpitcher[dpitcher["name"] == nm].iloc[0]
        lefty = d["throws"].iloc[0] == "L"
        for i, r in enumerate(d.itertuples()):
            c = PITCH_COLORS[i % len(PITCH_COLORS)]
            x, z = r.rx_mean, r.rz_mean
            ang = np.radians(r.arm_mean)
            dx = ARM_LEN_IN * np.cos(ang) * (1 if lefty else -1)
            ax.plot([x - dx, x], [z - ARM_LEN_IN * np.sin(ang), z], color=c, lw=2.5, alpha=0.85)
            ax.add_patch(Ellipse((x, z), 2 * r.sd_side_in, 2 * r.sd_height_in, facecolor=c, alpha=0.18,
                                 edgecolor=c, lw=1))
            ax.scatter(x, z, s=70, color=c, edgecolor="white", zorder=3,
                       label=f"{r.pitch_type}  {r.arm_mean:.0f}°  gap {r.release_gap_in:.1f} in")
        cx, cz = d["rx_mean"].mean(), d["rz_mean"].mean()
        ax.set_xlim(cx - 36, cx + 36)
        ax.set_ylim(cz - 40, cz + 14)
        ax.set_aspect("equal")
        ax.set_xlabel("Release side (in, catcher's view)")
        verdict = "consistent: every pitch from one slot" if summ["avg_release_gap_in"] <= 1.5 else \
            "inconsistent: the release tips the pitch"
        ax.set_title(f"{short(nm)} ({'L' if lefty else 'R'}HP): {verdict}\n"
                     f"avg release gap {summ['avg_release_gap_in']:.1f} in "
                     f"({ordinal(summ['avg_release_gap_in_pctile'])} pct, higher = tighter)",
                     loc="left", fontsize=10, color=KC_BLUE)
        ax.legend(frameon=False, fontsize=8, loc="lower left", title="pitch, arm angle, gap vs FB",
                  title_fontsize=8)
    axes[0].set_ylabel("Release height (in)")
    fig.suptitle("Delivery overlay: each pitch type's release point and arm slot, drawn on top of each other",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=DARK)
    fig.text(0.01, -0.02, "Dot = mean release point, shaded = 1 SD, line = arm drawn back from release at the mean "
             "Statcast arm angle (length for display only). Source: delivery_by_pitch.csv (Step 5A)",
             fontsize=6.5, color=DARK)
    fig.tight_layout()
    return save(fig, "slide3_delivery_overlay.png")


SAVANT_COLORS = {"FF": "#D22D49", "SI": "#FE9D00", "FC": "#933F2C", "SL": "#EEE716", "ST": "#DDB33A",
                 "SV": "#93AFD4", "CU": "#00D1ED", "KC": "#6236CD", "CH": "#1DBE3A", "FS": "#3BACAC",
                 "FO": "#55CCAB"}


def arsenal_grid(stuff: pd.DataFrame, scores: pd.DataFrame, pitchers: pd.DataFrame, title: str,
                 fname: str, ncols: int = 4):
    """Savant-style arsenal cards: movement (HB vs IVB) with dot size = usage, one panel per pitcher.

    pitchers: columns pitcher, label (display name). Only pitch types with 50+ pitches are drawn.
    """
    s = stuff[stuff["sample_flag"].fillna("").eq("")]
    sc = scores.drop_duplicates("pitcher").set_index("pitcher")
    n = len(pitchers)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.3 * ncols, 4.7 * nrows))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes[n:]:
        ax.axis("off")
    for ax, r in zip(axes, pitchers.itertuples()):
        mine = s[s["pitcher"] == r.pitcher].sort_values("usage_pct", ascending=False)
        ax.axhline(0, color=GRAY, lw=0.6)
        ax.axvline(0, color=GRAY, lw=0.6)
        for p in mine.itertuples():
            c = SAVANT_COLORS.get(p.pitch_type, DARK)
            ax.scatter(p.hb, p.ivb, s=30 + 9 * p.usage_pct, color=c, edgecolor=DARK, lw=0.7, alpha=0.9, zorder=3)
        lines = [f"{p.pitch_type:<3}{p.usage_pct:>3.0f}%  {p.velo:4.1f}  "
                 f"{'S+' + format(p.stuff_plus, '.0f') if pd.notna(p.stuff_plus) else ''}" for p in mine.itertuples()]
        ax.text(0.02, 0.02, "\n".join(lines), transform=ax.transAxes, fontsize=7, family="monospace",
                va="bottom", color=DARK, bbox=dict(facecolor="white", alpha=0.85, edgecolor="none", pad=2))
        for p in mine.itertuples():
            ax.annotate(p.pitch_type, (p.hb, p.ivb), xytext=(0, 0), textcoords="offset points", ha="center",
                        va="center", fontsize=6.5, fontweight="bold", color="white" if p.pitch_type in
                        {"FF", "FC", "KC", "CH", "FS"} else DARK, zorder=4)
        ax.set_xlim(-25, 25)
        ax.set_ylim(-25, 25)
        ax.set_aspect("equal")
        ax.tick_params(labelsize=7)
        hand = mine["throws"].iloc[0] if len(mine) else "?"
        sub = ""
        if r.pitcher in sc.index and pd.notna(sc.loc[r.pitcher, "stuff_score"]):
            sub = f"\nStuff {sc.loc[r.pitcher, 'stuff_score']:.0f} · Execution {sc.loc[r.pitcher, 'execution_score']:.0f}"
        ax.set_title(f"{r.label} ({hand}HP){sub}", loc="left", fontsize=9, color=KC_BLUE, fontweight="bold")
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=DARK)
    fig.text(0.01, -0.01, "Pitch movement, catcher's view: x = horizontal break (in), y = induced vertical break (in). "
             "Dot size = usage. Table: pitch, usage, avg velo (mph), FanGraphs Stuff+. Colors follow Baseball Savant. "
             "2026 relief pitches, 50+ per type. Source: stuff_by_pitch.csv", fontsize=7, color=DARK)
    fig.tight_layout()
    OUT = OUT_FIGS / "arsenal"
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / fname
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def featured_pitchers(leak, targets, fa_scored):
    """(KC qualified relievers, free-agent targets) as frames with pitcher, label."""
    kc = leak[leak["qualified"]].sort_values(["quadrant", "stuff_score"], ascending=[True, False])
    kc = pd.DataFrame({"pitcher": kc["pitcher"], "label": [f"{short(n)} · {q}" for n, q in zip(kc["reliever"],
                                                                                          kc["quadrant"])]})
    tg = fa_scored[fa_scored["name"].isin(set(targets["target"]))].dropna(subset=["pitcher"])
    tg = tg.assign(pitcher=tg["pitcher"].astype(int)).sort_values("stuff_score", ascending=False)
    tg = pd.DataFrame({"pitcher": tg["pitcher"], "label": tg["name"]})
    return kc, tg


def arsenal_sets(stuff, scores, leak, targets, fa_scored):
    kc, tg = featured_pitchers(leak, targets, fa_scored)
    return [arsenal_grid(stuff, scores, kc, "Royals relievers: pitch arsenals (2026, relief)",
                         "arsenal_kc_relievers.png", ncols=5),
            arsenal_grid(stuff, scores, tg, "Free-agent targets: pitch arsenals (2026, relief)",
                         "arsenal_fa_targets.png", ncols=4)]


# ---------------------------------------------------------------- pitch mix by count (Savant Pitch Mix view)

MIX_SMALL_N = 10  # counts with fewer pitches than this are drawn faded


def pitch_mix_card(mix: pd.DataFrame, pitcher: int, label: str, sub: str = "", fname: str | None = None):
    """Savant-style pitch mix: stacked usage bars for All and each of the 12 counts, for All / vs LHH / vs RHH."""
    from src.pitch_mix import COUNT_ORDER
    m = mix[mix["pitcher"] == pitcher]
    order = (m[(m["stand"] == "All") & (m["count"] == "All")].sort_values("n", ascending=False)["pitch_type"]
             .tolist())
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.6), sharey=True)
    for ax, (stand, head) in zip(axes, [("All", "All batters"), ("L", "vs LHH"), ("R", "vs RHH")]):
        g = m[m["stand"] == stand]
        y = np.arange(len(COUNT_ORDER))[::-1]
        for yi, cnt in zip(y, COUNT_ORDER):
            row = g[g["count"] == cnt].set_index("pitch_type")
            n = int(row["count_n"].iloc[0]) if len(row) else 0
            alpha = 0.35 if n < MIX_SMALL_N else 1.0
            left = 0.0
            for pt in order:
                if pt not in row.index:
                    continue
                w = float(row.loc[pt, "usage_pct"])
                ax.barh(yi, w, left=left, color=SAVANT_COLORS.get(pt, DARK), edgecolor="white", lw=0.8,
                        height=0.8 if cnt != "All" else 0.9, alpha=alpha)
                if w >= 12 and n >= MIX_SMALL_N:
                    ax.text(left + w / 2, yi, f"{w:.0f}", ha="center", va="center", fontsize=7.5,
                            color="white" if pt in {"FF", "FC", "KC", "CH", "FS"} else DARK, fontweight="bold")
                left += w
            ax.text(101.5, yi, f"{n}", va="center", fontsize=7, color=DARK if n >= MIX_SMALL_N else GRAY)
        ax.axhline(len(COUNT_ORDER) - 1.5, color=DARK, lw=0.6)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.tick_params(labelsize=8)
        ax.set_title(head, fontsize=10, color=DARK, fontweight="bold")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_yticks(np.arange(len(COUNT_ORDER))[::-1])
    axes[0].set_yticklabels(COUNT_ORDER, fontsize=8.5)
    axes[0].set_ylabel("Count (balls-strikes)", fontsize=9)
    handles = [plt.Rectangle((0, 0), 1, 1, color=SAVANT_COLORS.get(pt, DARK)) for pt in order]
    fig.legend(handles, order, loc="upper right", ncol=len(order), fontsize=9, frameon=False,
               bbox_to_anchor=(0.99, 1.0))
    fig.suptitle(f"{label}{sub}", x=0.01, ha="left", fontsize=13, fontweight="bold", color=KC_BLUE)
    fig.text(0.01, -0.02, "Pitch usage % by count, 2026 relief pitches (Baseball Savant Pitch Mix view, Savant colors). "
             f"Number at right = pitches in that count; faded rows have fewer than {MIX_SMALL_N}. "
             "Source: pitch_mix_by_count.csv", fontsize=7.5, color=DARK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    OUT = OUT_FIGS / "pitch_mix"
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (fname or f"pitch_mix_{pitcher}.png")
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def pitch_mix_sets(mix, scores, leak, targets, fa_scored):
    kc, tg = featured_pitchers(leak, targets, fa_scored)
    sc = scores.drop_duplicates("pitcher").set_index("pitcher")
    paths = []
    for r in pd.concat([kc, tg]).itertuples():
        if r.pitcher not in set(mix["pitcher"]):
            continue
        sub = ""
        if r.pitcher in sc.index and pd.notna(sc.loc[r.pitcher, "stuff_score"]):
            sub = f"   Stuff {sc.loc[r.pitcher, 'stuff_score']:.0f} · Execution {sc.loc[r.pitcher, 'execution_score']:.0f}"
        slug = re.sub(r"[^a-z]+", "_", r.label.split(" · ")[0].lower()).strip("_")
        paths.append(pitch_mix_card(mix, r.pitcher, r.label, sub, f"pitch_mix_{slug}.png"))
    return paths


# ---------------------------------------------------------------- pitch plinko (count tree)

PLINKO_SMALL_N = 10


def plinko_league(steps: pd.DataFrame, reach: pd.DataFrame, ids) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pooled league baseline in the same shape as one pitcher's rows (pitcher = 0)."""
    s = steps[steps["pitcher"].isin(set(ids))].groupby(["count", "step"])["n"].sum().reset_index()
    s["count_n"] = s.groupby("count")["n"].transform("sum")
    s["share_pct"] = (100 * s["n"] / s["count_n"]).round(1)
    r = reach[reach["pitcher"].isin(set(ids))]
    pa = r.drop_duplicates("pitcher")["pa"].sum()
    r = r.groupby("count")["pa_reached"].sum().reset_index().assign(pa=pa)
    r["reach_pct"] = (100 * r["pa_reached"] / pa).round(1)
    return s.assign(pitcher=0), r.assign(pitcher=0)


def _xy(b: int, s: int) -> tuple[float, float]:
    return b - s, -(b + s)


def plinko_card(steps, reach, lg_steps, lg_reach, pitcher: int, label: str, sub: str = "",
                fname: str | None = None, color: str = KC_BLUE):
    """Savant-style pitch plinko: every count a PA can pass through, sized by how often his PAs get there.

    Filled circle = this pitcher's reach %, dashed ring = league-average reliever. Arrows: share of pitches
    in that count that are balls (down-right) or strikes (down-left). Text under a node: share of pitches
    there that end the PA (in play / K / BB).
    """
    from src.plinko import summary
    st = steps[steps["pitcher"] == pitcher]
    rc = reach[reach["pitcher"] == pitcher].set_index("count")
    lrc = lg_reach.set_index("count")
    pa = int(rc["pa"].iloc[0])
    fig, ax = plt.subplots(figsize=(7.2, 7.6))
    def rad(pct: float) -> float:
        return 0.08 + 0.32 * np.sqrt(max(pct, 0.0) / 100)
    for b in range(4):
        for s in range(3):
            cnt = f"{b}-{s}"
            x, y = _xy(b, s)
            g = st[st["count"] == cnt].set_index("step")
            n = int(g["n"].sum()) if len(g) else 0
            for stp, (nb, ns) in {"ball": (b + 1, s), "strike": (b, s + 1)}.items():
                if nb > 3 or ns > 2 or stp not in g.index:
                    continue
                x2, y2 = _xy(nb, ns)
                share = float(g.loc[stp, "share_pct"])
                flow = float(g.loc[stp, "n"]) / pa
                ax.annotate("", (x2, y2 + 0.22), (x, y - 0.22), zorder=1,
                            arrowprops=dict(arrowstyle="-|>", lw=0.6 + 9 * flow, alpha=0.55,
                                            color=GRAY if stp == "ball" else color, shrinkA=0, shrinkB=0))
                if n >= PLINKO_SMALL_N:
                    ax.text((x + x2) / 2 + (0.16 if stp == "ball" else -0.16), (y + y2) / 2, f"{share:.0f}%",
                            ha="left" if stp == "ball" else "right", va="center", fontsize=7, color=DARK)
            r = float(rc["reach_pct"].get(cnt, 0.0)) if cnt in rc.index else 0.0
            lr = float(lrc["reach_pct"].get(cnt, 0.0)) if cnt in lrc.index else 0.0
            faded = n < PLINKO_SMALL_N
            ax.add_patch(plt.Circle((x, y), rad(r), facecolor=color, alpha=0.08 if faded else 0.22, zorder=3))
            ax.add_patch(plt.Circle((x, y), rad(r), fill=False, lw=2, color=color, alpha=0.4 if faded else 1,
                                    zorder=3))
            ax.add_patch(plt.Circle((x, y), rad(lr), fill=False, ls=(0, (2, 2)), lw=1, color=DARK, zorder=4))
            ax.text(x, y, f"{cnt}\n{r:.0f}%", ha="center", va="center", fontsize=8, fontweight="bold",
                    color=GRAY if faded else DARK, zorder=5)
            if n >= PLINKO_SMALL_N:
                ends = [(k, g["share_pct"].get(k, 0.0)) for k in ("in_play", "K", "BB")]
                txt = " · ".join(f"{'BIP' if k == 'in_play' else k} {v:.0f}" for k, v in ends if v >= 1)
                ax.text(x, y - 0.47, txt, ha="center", va="top", fontsize=6.3, color=DARK, zorder=5)
    ax.set_xlim(-2.8, 3.8)
    ax.set_ylim(-5.75, 0.65)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(-2.7, 0.45, "\u2199 strike", fontsize=8, color=color, fontweight="bold")
    ax.text(3.7, 0.45, "ball \u2198", fontsize=8, color=GRAY, fontweight="bold", ha="right")
    me, lg = summary(st, rc.reset_index(), pitcher), summary(lg_steps, lg_reach, 0)
    line = (f"PAs {me['pa']}   K {me['k_pct']:.0f}% (lg {lg['k_pct']:.0f})   BB {me['bb_pct']:.0f}% "
            f"(lg {lg['bb_pct']:.0f})   0-1 after pitch one {me['reach_0_1']:.0f}% (lg {lg['reach_0_1']:.0f})   "
            f"3-ball counts {me['reach_3_x']:.0f}% (lg {lg['reach_3_x']:.0f})")
    fig.suptitle(f"{label}{sub}", x=0.02, y=0.99, ha="left", fontsize=12, fontweight="bold", color=color)
    fig.text(0.02, 0.945, line, fontsize=7.6, color=DARK)
    fig.text(0.02, 0.01, "Circle = share of his PAs that reach the count (dashed ring = league-average reliever). "
             "Arrow % = pitches in that count that are\nstrikes (incl. fouls) or balls; under each count, % of "
             f"pitches there that end the PA. Faded = fewer than {PLINKO_SMALL_N} pitches. 2026 relief. "
             "Source: plinko_steps.csv, plinko_reach.csv", fontsize=6.3, color=DARK)
    OUT = OUT_FIGS / "plinko"
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (fname or f"plinko_{pitcher}.png")
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def plinko_sets(steps, reach, scores, leak, targets, fa_scored, prospects=None, names=None):
    """One plinko per KC reliever, free-agent target and prospect with MLB pitches, plus the scoreboard."""
    from src.plinko import summary
    kc, tg = featured_pitchers(leak, targets, fa_scored)
    kc = kc.assign(group="KC reliever")
    tg = tg.assign(group="Free-agent target")
    frames = [kc, tg]
    if prospects is not None:
        flip = {f"{n.split(', ')[1]} {n.split(', ')[0]}": pid for n, pid in zip((names if names is not None else scores)["name"],
                                                                     (names if names is not None else scores)["pitcher"])
                if isinstance(n, str) and ", " in n}
        pr = prospects.assign(pitcher=prospects["pitcher"].fillna(prospects["name"].map(flip)))
        pr = pr.dropna(subset=["pitcher"])
        pr = pr[~pr["pitcher"].astype(int).isin(set(kc["pitcher"]))]
        frames.append(pd.DataFrame({"pitcher": pr["pitcher"].astype(int), "label": pr["name"] + " · prospect",
                                    "group": "Prospect"}))
    who = pd.concat(frames, ignore_index=True)
    who = who[who["pitcher"].isin(set(reach["pitcher"]))]
    q = scores.loc[scores["qualified"].astype(bool), "pitcher"]
    lg_s, lg_r = plinko_league(steps, reach, q)
    sc = scores.drop_duplicates("pitcher").set_index("pitcher")
    paths, rows = [], []
    for r in who.itertuples():
        sub = ""
        if r.pitcher in sc.index and pd.notna(sc.loc[r.pitcher, "execution_score"]):
            sub = f"   Execution {sc.loc[r.pitcher, 'execution_score']:.0f}"
        slug = re.sub(r"[^a-z]+", "_", r.label.split(" · ")[0].lower()).strip("_")
        color = KC_BLUE if r.group == "KC reliever" else ("#BD9B60" if r.group == "Prospect" else DARK)
        paths.append(plinko_card(steps, reach, lg_s, lg_r, r.pitcher, r.label, sub, f"plinko_{slug}.png", color))
        rows.append({"pitcher": r.pitcher, "label": r.label.split(" · ")[0], "group": r.group,
                     **summary(steps, reach, r.pitcher)})
    board = pd.DataFrame(rows)
    board.to_csv(OUT_TABLES / "plinko_summary.csv", index=False)
    paths.append(plinko_board(board, summary(lg_s, lg_r, 0)))
    return paths


def plinko_board(board: pd.DataFrame, lg: dict):
    """One-glance table: how each pitcher's PAs travel (first-strike, 0-2, 3-ball, K, BB) vs league."""
    cols = [("reach_0_1", "0-1 after\npitch one", True), ("reach_0_2", "Reach\n0-2", True),
            ("reach_3_x", "Reach a\n3-ball count", False), ("k_pct", "K%", True), ("bb_pct", "BB%", False)]
    b = board.copy()
    fig, ax = plt.subplots(figsize=(8.6, 0.32 * len(b) + 1.2))
    vals = np.array([[b.iloc[i][c] - lg[c] for c, _, _ in cols] for i in range(len(b))], dtype=float)
    sign = np.array([1 if good else -1 for _, _, good in cols])
    colors = np.clip(vals * sign / 12, -1, 1)
    ax.imshow(colors, cmap="RdBu", vmin=-1, vmax=1, aspect="auto")
    for i in range(len(b)):
        for j, (c, _, _) in enumerate(cols):
            ax.text(j, i, f"{b.iloc[i][c]:.0f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(colors[i, j]) > 0.6 else DARK)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([f"{h}\n(lg {lg[c]:.0f})" for c, h, _ in cols], fontsize=8)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(b)))
    ax.set_yticklabels([f"{short(n) if ',' in n else n}  ({g.replace(" reliever", "")}, {pa} PA)" for n, g, pa in
                        zip(b["label"], b["group"].replace({"Free-agent target": "FA target"}), b["pa"])], fontsize=8)
    for i, g in enumerate(b["group"]):
        if i and g != b["group"].iloc[i - 1]:
            ax.axhline(i - 0.5, color=DARK, lw=1.2)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.text(0.01, 0.0, "Percent of PAs. Blue = better than the league-average reliever, red = worse. "
             "Source: plinko_summary.csv", fontsize=7, color=DARK)
    fig.tight_layout()
    path = OUT_FIGS / "plinko" / "plinko_scoreboard.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- Statcast expected stats (ERA vs xERA)

def expected_stats_chart(xs: pd.DataFrame, leak, targets, fa_scored, prospects=None):
    """ERA vs xERA and wOBA vs xwOBA (Savant expected-stats export) for KC relievers and targets."""
    kc, tg = featured_pitchers(leak, targets, fa_scored)
    who = pd.concat([kc.assign(group="KC"), tg.assign(group="FA target")], ignore_index=True)
    x = xs.rename(columns={"player_id": "pitcher"}).merge(who, on="pitcher")
    for c in ("era", "xera", "woba", "est_woba"):
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.sort_values(["group", "xera"], ascending=[False, False]).reset_index(drop=True)
    fig, axes = plt.subplots(1, 2, figsize=(11, 0.42 * len(x) + 1.4), sharey=True)
    y = np.arange(len(x))
    for ax, (a, e, head, fmt) in zip(axes, [("era", "xera", "ERA → xERA", "{:.2f}"),
                                            ("woba", "est_woba", "wOBA → xwOBA", "{:.3f}")]):
        for i, r in x.iterrows():
            col = KC_BLUE if r["group"] == "KC" else DARK
            ax.plot([r[a], r[e]], [i, i], color=GRAY, lw=2, zorder=1)
            ax.scatter(r[a], i, s=40, facecolor="white", edgecolor=col, lw=1.5, zorder=2)
            ax.scatter(r[e], i, s=55, color=col, zorder=3)
            ax.text(r[e], i + 0.3, fmt.format(r[e]).lstrip("0") if a == "woba" else fmt.format(r[e]),
                    ha="center", fontsize=7, color=col)
        ax.set_title(head, fontsize=10, color=DARK, fontweight="bold", loc="left")
        ax.tick_params(labelsize=8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.grid(axis="x", color=GRAY, alpha=0.25)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([f"{short(n)} ({g}, {pa} PA)" for n, g, pa in
                             zip(x["last_name, first_name"], x["group"], x["pa"])], fontsize=8)
    missing = who[~who["pitcher"].isin(set(x["pitcher"]))]
    fig.suptitle("Statcast expected stats: who was unlucky, who was lucky", x=0.01, ha="left", fontsize=12,
                 fontweight="bold", color=DARK)
    note = ("Hollow = actual, filled = expected (from exit velocity, launch angle, K and BB). Filled left of hollow = "
            "unlucky. 2026, all roles, Savant export (min. PA in export: "
            f"{int(xs['pa'].min())}). Not in export: {', '.join(short(n) for n in missing['label'].str.split(' · ').str[0])}.")
    fig.text(0.01, -0.02, note, fontsize=7, color=DARK, wrap=True)
    fig.tight_layout()
    path = OUT_FIGS / "expected_stats.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------- slide 5

def slide5_targets(targets: pd.DataFrame):
    t = targets.sort_values(["kc_reliever", "rank"])
    rows = []
    for kc_name, g in t.groupby("kc_reliever", sort=False):
        first = g.iloc[0]
        fits = "\n".join(f"{r.target} ({r.throws}, {r.age}) {r.match_on} {r.target_pctile:.0f}th pct"
                         for r in g.itertuples())
        leak = re.sub(r"^(Execution|Stuff|Smallest gap): ", "", first["leak"])
        leak = re.sub(r"\((\d+\w\w pct)[^)]*\)", r"(\1)", leak)
        rows.append([short(kc_name), first["reason"].replace("KC free agent: ", "FA: ").replace("replace candidate", "Replace candidate"), leak, fits])
    fig, ax = plt.subplots(figsize=(12, 0.75 * len(rows) + 0.8))
    ax.axis("off")
    tab = ax.table(cellText=rows, colLabels=["Royals reliever", "Decision", "Leak", "Top free-agent fits"],
                   colWidths=[0.11, 0.17, 0.30, 0.42], bbox=[0, 0, 1, 1], cellLoc="left")
    tab.auto_set_font_size(False)
    tab.set_fontsize(7.5)
    for (i, j), cell in tab.get_celld().items():
        cell.set_edgecolor("#DDDDDD")
        if i == 0:
            cell.set_facecolor(KC_BLUE)
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")
        elif j == 0:
            cell.get_text().set_color(KC_BLUE)
            cell.get_text().set_fontweight("bold")
    ax.set_title("Replacement targets matched to each leak (2026-27 free agents)", loc="left", fontsize=12)
    fig.text(0.01, -0.03, "Ranked on the reliever's leak metric among qualified free agents in the Keep quadrant, "
             "age 35 or under where possible. Source: targets.csv", fontsize=6.5, color=DARK)
    return save(fig, "slide5_targets.png")


# ---------------------------------------------------------------- run

def main() -> int:
    from src.leak_map import execution_scores, stuff_scores
    T = OUT_TABLES
    ranks = pd.read_csv(T / "team_bullpen_ranks_2026.csv")
    kc_team = "KCR" if "KCR" in set(ranks["Team"]) else "KC"
    leak = pd.read_csv(T / "leak_map.csv")
    scores = pd.read_csv(T / "scores_all_relievers.csv")
    stuff = pd.read_csv(T / "stuff_by_pitch.csv")
    exe = pd.read_csv(T / "execution_by_reliever.csv")
    exe_good = execution_scores(exe)[["pitcher"] + [c for c, _ in HEAT_COLS if c.endswith("_good")]]
    parts = stuff_scores(stuff)[["pitcher", "primary_fb_pctile", "best_secondary_pctile"]]
    kc_ids = leak.loc[leak["qualified"], "pitcher"]
    paths = [
        slide1_ranks(ranks, kc_team),
        slide2_scatter(scores, leak),
        slide2_heatmap(leak, exe_good, parts),
        slide3_movement(stuff, leak),
        slide3_tunnel(pd.read_csv(T / "sequence_pairs.csv")),
        slide3_sequence_heatmap(pd.read_csv(T / "sequence_summary.csv"), kc_ids),
        slide3_often_vs_well(pd.read_csv(T / "sequencing_triage.csv"), leak, scores),
        delivery_overlay(pd.read_csv(T / "delivery_by_pitch.csv"), pd.read_csv(T / "delivery_by_pitcher.csv"),
                         ["Erceg, Lucas", "Strahm, Matt"]),
    ]
    if (T / "targets.csv").exists():
        paths.append(slide5_targets(pd.read_csv(T / "targets.csv")))
        paths += arsenal_sets(stuff, scores, leak, pd.read_csv(T / "targets.csv"),
                              pd.read_csv(T / "fa_relievers_scored.csv"))
        if (T / "pitch_mix_by_count.csv").exists():
            paths += pitch_mix_sets(pd.read_csv(T / "pitch_mix_by_count.csv"), scores, leak,
                                    pd.read_csv(T / "targets.csv"), pd.read_csv(T / "fa_relievers_scored.csv"))
        if (T / "plinko_steps.csv").exists():
            pros = pd.read_csv(T / "prospects_pitchers.csv") if (T / "prospects_pitchers.csv").exists() else None
            paths += plinko_sets(pd.read_csv(T / "plinko_steps.csv"), pd.read_csv(T / "plinko_reach.csv"), scores,
                                 leak, pd.read_csv(T / "targets.csv"), pd.read_csv(T / "fa_relievers_scored.csv"),
                                 pros, names=exe[["pitcher", "name"]])
    xs_path = ROOT / "data" / "manual" / "expected_stats.csv"
    if xs_path.exists() and (T / "targets.csv").exists():
        paths.append(expected_stats_chart(pd.read_csv(xs_path, encoding="utf-8-sig"), leak,
                                          pd.read_csv(T / "targets.csv"), pd.read_csv(T / "fa_relievers_scored.csv")))
    for p in paths:
        print(p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
