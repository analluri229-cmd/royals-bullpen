"""Split each FanGraphs Excel export in data/manual into one CSV per tab.

FanGraphs exports one leaderboard tab at a time, so the manual exports are
saved as workbooks with one sheet per tab (Dashboard, Advanced, Stuff+, ...).
This writes data/manual/<workbook>_<tab>.csv for every sheet, e.g.
fg_relievers_2026.xlsx [Stuff+] -> fg_relievers_2026_stuff_plus.csv.
fangraphs.py merges those tab CSVs back into one table per input.

Usage:  python -m src.split_fg_workbooks
"""
from __future__ import annotations

import re
import sys

import pandas as pd

from src.config import DATA_MANUAL


def tab_slug(sheet: str) -> str:
    """'Stuff+' -> 'stuff_plus', 'Location+' -> 'location_plus', 'Dashboard' -> 'dashboard'."""
    s = sheet.strip().lower().replace("+", "_plus")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def split(workbook) -> list:
    out = []
    for sheet, df in pd.read_excel(workbook, sheet_name=None).items():
        path = workbook.with_name(f"{workbook.stem}_{tab_slug(sheet)}.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")  # BOM so Excel shows accents
        print(f"{workbook.name} [{sheet}] {df.shape[0]} rows x {df.shape[1]} cols -> {path.name}")
        out.append(path)
    return out


def main(argv=None) -> int:
    books = sorted(DATA_MANUAL.glob("fg_*.xlsx"))
    if not books:
        print(f"no fg_*.xlsx in {DATA_MANUAL}")
    for book in books:
        split(book)
    return 0


if __name__ == "__main__":
    sys.exit(main())
