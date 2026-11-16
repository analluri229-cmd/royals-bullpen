# Handoff: where this project stands (2026-10-31)

Read this together with `CLAUDE.md` at the start of a new session.

## Done so far
- Read the spec (now in `CLAUDE.md`) and checked which skills cover each step.
- Created the Step 0 folders: `data/raw`, `data/manual`, `data/processed`, `src`, `notebooks`, `outputs/figures`, `outputs/tables`, `tests`, `notes`, `.vscode`.
- Found that a full 2026 regular-season Statcast pull already exists:
  - Original: `C:\Users\themi\source\repos\statcast_data_2026.csv` (~408 MB, every Savant column, including `arm_angle`, bat tracking, `age_pit` and `umpire`). It was pulled by `repos\Pull-Statcast-2026.R` for 2026-03-25 to 2026-09-27, game_type R.
  - Compressed copy: `data/raw/statcast_2026.csv.gz` (~168 MB). **This means Step 3 needs no new pull.** Convert it to `data/raw/statcast_2026.parquet` with only the columns Step 3 keeps. Check whether the `umpire` column is actually filled in.
- Checked the existing pull: 597,515 regular-season pitches in 2,038 games, but it **starts 2026-04-25**, so 2026-03-25 to 2026-04-24 (about 390 games) is missing. The `umpire` column is 0% filled.
- 2026-10-31: Next steps 1 and 2 are done (except running the live pulls on Windows). Scaffolding, `git init` on `main` (no remote yet), and `src/build_statcast_parquet.py`, `src/pull_statcast.py`, `src/relievers.py`, `src/fangraphs.py`, with 16 passing unit tests. See `notes/decisions.md`.
- Step 1 dry run on the existing file: 320 of 707 MLB relievers qualify, and 10 KC relievers qualify (Cruz, Lange, Schreiber, Erceg, Lynch, Black, Strahm, Pearson, Cuas, Way), with 21 small samples. Rerun after the missing month is filled.

- 2026-11-01: Step 6 leak map (`python -m src.leak_map`, branch step-6-leak-map). KC: Keep = Cruz, Strahm. Execution fix = Avila, Schreiber, Lynch, Way, Pearson, Cuas, Lange. Replace candidates = Mears, Black, Erceg, Morgan. The bullpen's leak is execution, not stuff: 9 of 13 have above-average Stuff, but 11 of 13 are below average on Execution. Still open: 2024-25 velocity trend and the contracts file.
- 2026-11-01: Step 7 free-agent targets (`python -m src.targets`). Morejon, Phillips and Fairbanks top most leak matches; Strahm and Schreiber are KC free agents. Prospects are still to come.
- 2026-11-07: Step 7b trade targets (`python -m src.trade_targets`). Same leak matching as the free-agent list, run on the 273 qualified relievers on other teams who aren't free agents. Top fits: Andres Munoz (SEA), Daniel Duarte (NYM), Mason Miller (SD), Jacob Latz (TEX), Jhoan Duran (PHI), Drew Sommers (DET). Team control isn't in Statcast: fill `data/manual/trade_control_2026_template.csv` (control_through, status, salary_2027_m from Spotrac or RosterResource), save it as `trade_control_2026.csv`, and rerun. Anyone whose control ends in 2026 then drops out.

## Known limits
- The Claude cloud workspace can't reach Baseball Savant, FanGraphs or the MLB Stats API. Neither can the Linux shell on the laptop. Data pulls run in VS Code on Windows, or the data comes in as manual exports.
- FanGraphs inputs (team reliever ranks, player Stuff+ / Location+ / Pitching+, wRC+, Def) are exported by hand to `data/manual/fg_team_relievers_2026.csv` and `data/manual/fg_relievers_2026.csv`.
- Other manual files: `data/manual/fa_relievers_2026.csv` (MLB Trade Rumors), `data/manual/royals_contracts.csv`, `data/manual/royals_prospects.csv` (FanGraphs The Board), and `data/manual/aaa_statcast_2026.csv` (Savant minors search).

## Skills to use, by step
| Step | Skill / tool |
|---|---|
| 0: Setup | claude-md-composer, project-memory |
| 1-5A: Metrics | data:statistical-analysis, data:explore-data, analytics-office:kpi-contract (pin down 3PS%, LiVAA) |
| 6-7: Leak map and targets | analytics-office:audit-my-assumptions, data:analyze |
| 8: Figures | dataviz, data:create-viz |
| Deck | Slides artifact first, then the pptx skill |
| Scouting appendix | Docs artifact |
| 9: Validation | data:validate-data, analytics-office:defend-my-number |

## Next steps
0. On Windows: create the GitHub repo `royals-bullpen` on analluri229-cmd, then `git remote add origin ...` and push. Make the venv, then run `python -m src.pull_statcast --start 2026-03-25 --end 2026-04-24`, `python -m src.build_statcast_parquet --force`, `python -m src.relievers` and `python -m src.fangraphs`. Export the FanGraphs CSVs by hand if the live pull fails.
1. (done) Add `requirements.txt` (pandas, numpy, pybaseball, pyarrow, matplotlib, seaborn, scipy, statsmodels, jupyter, pytest), `.gitignore` (ignore `data/`, `.venv/`, `.env`), `README.md` from the `_project-template` layout, and `notes/decisions.md`. Run `git init` (repos go on the analluri229-cmd GitHub account).
2. (scripts done, needs a Windows run) Steps 1-3: build the parquet, the reliever flag (not the team's first pitcher per game_pk) and the KC reliever list (20+ relief IP or 300+ pitches). Write the FanGraphs pull script with a manual-CSV fallback.
3. Steps 4 → 5 → 5A (Core) → 6 → 7 → 8 → deck (Slides, then .pptx) → 9.
