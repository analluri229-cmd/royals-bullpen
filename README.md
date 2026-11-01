# Royals Bullpen Revitalization

**Question:** How should the Royals revitalize their bullpen? Which relievers are fixable, what exactly should be fixed, and who should be replaced?

**Answer in one sentence:** (write this last)

## Data
- Statcast pitch-level data, 2026 regular season, from Baseball Savant (pulled with pybaseball and the Savant CSV search). Use follows Baseball Savant's terms.
  - `data/raw/statcast_2026.csv.gz`: existing full-column pull (2026-04-25 to 2026-09-27).
  - `data/raw/statcast_chunks/`: 7-day chunks from `src/pull_statcast.py` (fills 2026-03-25 to 2026-04-24).
  - `data/raw/statcast_2026.parquet`: slim, merged file built by `src/build_statcast_parquet.py`.
- FanGraphs 2026 reliever stats (team and player, including Stuff+, Location+, Pitching+), plus team wRC+ and Def. Pulled live when possible, otherwise exported by hand to `data/manual/`.
- Manual inputs (Step 6 and Step 7): `fa_relievers_2026.csv` (MLB Trade Rumors), `royals_contracts.csv`, `royals_prospects.csv` (FanGraphs The Board), `aaa_statcast_2026.csv` (Savant minors search).
- `data/` is not committed. The full spec is in `CLAUDE.md`.

## Method
1. Scope (Step 1): a reliever is any pitcher who isn't his team's first pitcher of the game. KC relievers need 20+ relief IP or 300+ relief pitches. Smaller samples are listed and flagged.
2. Outcome layer (Step 2): FanGraphs bullpen ranks 1 to 30 across WAR, ERA, FIP, xFIP, SIERA, K%, BB%, K-BB%, WHIP and HR/9.
3. Pitch data (Step 3): one regular-season Statcast parquet with the columns listed in `CLAUDE.md`.
4. Stuff, Execution and sequencing metrics (Steps 4, 5 and 5A), then the leak map, targets, figures and validation (Steps 6 to 9).

## Findings
(2 to 3 charts from `outputs/`, each with one sentence saying what it shows)

## Decisions log
See `notes/decisions.md`.

## Limitations
- Statcast can't see tempo or mechanics, so delivery findings need video review.
- Reliever samples are small for pitch-pair metrics. Stretch sequencing patterns are directional only.
- Umpire IDs aren't filled in the Statcast pull.

## What I would do next

## How to run
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python -m src.pull_statcast --start 2026-03-25 --end 2026-04-24   # fill the missing month
python -m src.build_statcast_parquet --force                       # Step 3
python -m src.relievers                                            # Step 1
python -m src.split_fg_workbooks                                   # FanGraphs .xlsx exports -> one CSV per tab
python -m src.fangraphs                                            # Step 2 (add --offline to use manual CSVs)
python -m src.stuff                                                # Step 4 -> outputs/tables/stuff_by_pitch.csv
python -m src.deception                                            # Step 5A delivery + tunneling
python -m src.execution                                            # Step 5 -> outputs/tables/execution_by_reliever.csv
python -m src.leak_map                                             # Step 6 -> outputs/tables/leak_map.csv
python -m src.targets                                              # Step 7 -> outputs/tables/targets.csv (needs data/manual/fa_relievers_2026.csv)
python -m src.prospects                                            # Step 7 -> outputs/tables/prospects_pitchers.csv (needs data/manual/royals_prospects.csv)
python -m pytest
```

Outputs: `outputs/tables/kc_relievers_2026.csv`, `league_relievers_2026.csv` and `team_bullpen_ranks_2026.csv`.
