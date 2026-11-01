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
    for p in paths:
        print(p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
