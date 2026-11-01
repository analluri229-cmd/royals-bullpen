"""Download MLB headshots for the pitchers named in the deck (run on Windows; the cloud can't reach MLB).

Who: qualified KC relievers (leak_map.csv) and every free-agent target (targets.csv),
looked up by MLBAM id. Files are cached: an existing file is never downloaded again.

Images are MLB's (img.mlbstatic.com). Fine for a private portfolio video; check
MLB's terms before posting anything publicly.

Usage:  python -m src.fetch_headshots
"""
from __future__ import annotations

import sys
import urllib.request

import pandas as pd

from src.config import OUT_TABLES, ROOT

OUT_DIR = ROOT / "outputs" / "headshots"
URL = ("https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/"
       "w_426,q_auto:best/v1/people/{pid}/headshot/67/current")


def wanted() -> pd.DataFrame:
    leak = pd.read_csv(OUT_TABLES / "leak_map.csv")
    kc = leak.loc[leak["qualified"], ["pitcher", "reliever"]].rename(columns={"reliever": "name"})
    fa = pd.read_csv(OUT_TABLES / "fa_relievers_scored.csv")
    tg = pd.read_csv(OUT_TABLES / "targets.csv")
    fa = fa[fa["name"].isin(set(tg["target"]))][["pitcher", "name"]]
    out = pd.concat([kc, fa]).dropna(subset=["pitcher"]).drop_duplicates("pitcher")
    out["pitcher"] = out["pitcher"].astype(int)
    return out


def file_name(name: str, pid: int) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")
    return f"{slug}_{pid}.png"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for r in wanted().itertuples():
        path = OUT_DIR / file_name(r.name, r.pitcher)
        if path.exists():
            continue
        try:
            req = urllib.request.Request(URL.format(pid=r.pitcher), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                path.write_bytes(resp.read())
            print("saved", path.name)
        except Exception as exc:  # keep going; report the misses
            print("failed", r.name, r.pitcher, exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
