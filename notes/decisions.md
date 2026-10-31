# Decisions log (copy into README at the end)

- 2026-10-31: Project root is `C:\Users\themi\source\royals-bullpen`, outside OneDrive, so large data files don't sync.
- 2026-10-31: Real data only, never synthetic class data. Small hand-built games in `tests/` only check code logic and are never analyzed.
- 2026-10-31: Step 3 reuses the existing full-column pull (`data/raw/statcast_2026.csv.gz`) rather than re-pulling. Checked it: 597,515 regular-season pitches in 2,038 games, but it runs from 2026-04-25 to 2026-09-27, so about a month (2026-03-25 to 2026-04-24) is missing. `src/pull_statcast.py` fills that window in 7-day chunks, and `src/build_statcast_parquet.py` merges and de-duplicates it.
- 2026-10-31: The `umpire` column exists but is 0% filled. Pattern 10 (umpire sequencing) needs umpire IDs from the MLB Stats API game feed, or gets cut as a Stretch pattern.
- 2026-10-31: Added `inning` to the Step 3 keep list. Relief IP needs outs by half-inning.
- 2026-10-31: Reliever = not the team's first pitcher of the game (earliest pitch per game_pk and pitching team). Openers therefore count as starters, and the bulk pitcher after an opener counts as a reliever. Revisit if KC used openers often.
- 2026-10-31: Relief IP = outs recorded / 3. Outs per PA = next PA's outs_when_up minus this PA's in the same half-inning, or 3 at the end of the half. This credits caught stealing and pickoff outs too. In a game's final half-inning with the home team batting (walk-offs), outs come from the event instead. A mid-PA pitching change credits the whole PA to the first pitcher. Step 9 checks totals against FanGraphs (within 2%).
- 2026-10-31: KC reliever totals count only appearances for KC (a pitcher traded in or out counts only his KC innings). League totals count all relief for every team.
- 2026-10-31: FanGraphs pulls try live first, then fall back to manual exports in `data/manual/`. Team abbreviation is `KC` in Statcast and `KCR` in FanGraphs.
- 2026-10-31: Step 4 uses relief pitches only. A KC reliever's pitches count only from his KC appearances.
- 2026-10-31: LiVAA is fit (VAA on plate_z, one line per pitch group FB/BRK/OFF) on qualified league relievers' pitches only, so small samples don't steer the slope. The method is still to confirm with the mentor.
- 2026-10-31: Step 4 percentiles are raw (100 = highest value) against qualified relievers with 50+ pitches of the same pitch type, thrown with the same hand. Which direction counts as good (flatter VAA, more IVB on a fastball, and so on) is decided in Step 6.
- 2026-10-31: FanGraphs Stuff+ is joined by MLBAM ID when the export has one, otherwise by normalized name. FanGraphs folds sweepers into SL, so ST pitches get the SL Stuff+. CU Stuff+ also covers KC unless a KC column exists.
