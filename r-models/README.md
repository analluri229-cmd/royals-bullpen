# Is it real? Strike-throwing models for the Royals bullpen (R)

This folder adds a modeling layer to the Royals bullpen project. The Python pipeline found that the bullpen's main leak is execution, not stuff, and several relievers were tagged as having a strike-throwing problem. Most relievers face only 80 to 280 batters in a season, so a raw rate like F-Strike% swings a lot on luck. This part asks two questions a pitching coach would ask before spending time on a fix:

1. **Is his first-pitch strike problem real, or is it noise from a small sample?**
2. **Is he losing borderline strike calls, and on which edge of the zone?**

## How it works

| Step | Tool | What it does |
|---|---|---|
| Database | DuckDB + hand-written SQL (`sql/`) | Loads the 2026 Statcast parquet and builds the tables: relief PAs with their first pitch, every taken pitch with its distance from the zone edge, and the reliever groups from Step 1. |
| First-pitch strike model | `lme4` mixed-effects logistic regression | Each relief PA's first pitch, with random effects for pitcher, batter and catcher, and platoon, runners on and late innings as context. The pitcher effect is his talent, pulled toward league average in proportion to how little data he has. |
| Bayesian version | `brms` (Stan) | The same model in a Bayesian form, which gives each reliever a full posterior. That makes a statement like "an 85% chance his true rate is below average" possible. |
| Validation | Split-half check | Fits the model on games before July 1 and predicts each reliever's rate after July 1. If shrinkage works, it beats the raw first-half rate. |
| Leak map check | Re-score of Step 6 | Swaps the model's F-Strike% into the Step 6 execution score, using the same percentile rules as the Python code, and shows who changes quadrant. The R rebuild of the Python score is checked against `scores_all_relievers.csv`. |
| Called-strike model | `mgcv::bam` GAM with random effects | Learns the zone umpires actually call from every taken pitch in 2026, with a separate shape for each pitcher and batter hand pairing, count adjustments, and random effects for catcher and pitcher. Called strikes above expected (CSAE) compares the calls a reliever got with what a league-average pitcher and catcher would get on the same pitches. |
| Coach app | Shiny (`app/`) | Pick a reliever and see his first-pitch verdict, his called-strike map and edge table, and whether the leak map changes, each with a one-line takeaway in plain language. |

## Results

From the first full run on 2026 Statcast (79,479 relief PAs and 332,923 taken pitches). Every number below is in `outputs/tables/r_models/`. Intervals for qualified and Royals relievers come from the Bayesian brms model (90%), and "chance below average" is its posterior probability. The brms fit converged cleanly: Rhat at most 1.003, bulk ESS at least 758, and 1 divergent transition in 4,000 draws. It agrees with lme4 to within 0.3 points for all 352 qualified relievers (correlation 0.999), even though it drops the batter effect.

**1. One season of a reliever's F-Strike% is mostly noise.** The true spread between relievers is small: one standard deviation is about 2.9 points (pitcher SD 0.12 on the logit scale in both lme4 and brms) around a 61.1% league rate (`fstrike_variance.csv`). A reliever needs about 279 PAs before his observed rate is half signal. Lange (276 PA) is the only Royals reliever close to that.

**2. The raw first-half rate predicts the second half worse than just guessing league average.** Across 296 relievers with 20+ PA in each half, the raw first-half rate misses by 7.2 points (RMSE). League average misses by 5.8, and the mixed model by 5.6 (`fstrike_split_half.csv`, `fstrike_split_half.png`). The model is the only one of the three that beats league average.

**3. No Royals reliever's first-pitch problem is clearly real.** None has a 90%+ chance of being truly below average. Pearson (86%) and Lynch (85%) are the most likely, and both have 180+ PA. Avila's 55.1% shrinks to 59.8% (90% interval 55.4 to 64.1), with a 69% chance he's below average. So the Step 6 label "F-Strike% is Avila's primary leak" rests on 78 PAs and is weak. Mears (53.7% raw, 82 PA) moves the most, to 59.4%. See `fstrike_shrinkage_kc.png`.

**4. The leak map holds up.** With the model's F-Strike% swapped in, no Royals reliever changes quadrant, and 10 of 335 qualified league relievers do (`execution_rescore.csv`). F-Strike% is one of six execution metrics, so the other five carry each Royals verdict. The R rebuild matches the Python execution score exactly (max difference 0.00 over 437 relievers).

**5. Called strikes: the zone model is strong, and pitcher effects are small.** The GAM explains 80.5% of the deviance in called strikes. On edge pitches (within 3 inches of the border), Morgan (+14.3 per 100 takes, only 46 takes) and Mears (+8.9) got the most extra strikes. Strahm, Pearson, Cruz and Black each lost about 4.7. The part the model gives to the pitcher himself is within ±2 per 100 for every Royals reliever. Catchers range from −3.4 to +3.3 per 100 (`catcher_framing.csv`). Most of a reliever's CSAE is noise or pitch mix, not a skill to coach. Edge-by-region cells rarely reach 40 takes in a relief season (`kc_edge_csae.png`), so treat them as directional.

**What it means for the plan.** Coach first-pitch strikes where the evidence is strongest: Pearson and Lynch. For Avila and Mears, collect more innings before calling F-Strike% the fix. Their execution scores are low for other reasons.

## Run it

From the repo root, after the Python Step 1, 5 and 6 scripts have run:

```
Rscript r-models/install.R          # one time
Rscript r-models/tests/testthat.R   # unit tests (no data needed)
Rscript r-models/run_all.R          # database, models, tables, figures
Rscript -e "shiny::runApp('r-models/app')"
```

`run_all.R` caches the database (`data/processed/bullpen.duckdb`) and each model fit (`data/processed/r_models/`), so the second run takes seconds. Pass `--rebuild` to start over. Set `BULLPEN_SKIP_BRMS=1` to skip the Stan fit, and the lme4 intervals are used in its place.

Outputs:
- `outputs/tables/r_models/`: `fstrike_estimates.csv`, `fstrike_split_half.csv`, `fstrike_variance.csv`, `execution_rescore.csv`, `csae_by_pitcher.csv`, `csae_by_region.csv`, `catcher_framing.csv`, `zone_grid.csv`, and the GAM summary.
- `outputs/figures/r_models/`: 300 dpi PNGs in Royals blue and league gray.

## Choices and limits

- **The PA goes to the pitcher of its first pitch.** The Python Step 5 code credits the pitcher of the last pitch. They differ only when a pitching change happens mid-PA.
- **A traded reliever's model estimate uses all of his relief work.** The Python KC rows use KC appearances only. The model needs the full sample to estimate talent.
- **The brms model leaves out the batter effect** and fits on PAs grouped into pitcher by catcher by context cells, so it runs in minutes instead of hours. The lme4 model keeps the batter effect, and the two agree closely.
- **Umpires aren't in the called-strike model.** The umpire column in this Statcast pull is empty (see `notes/decisions.md`). Adding umpire IDs from the MLB Stats API game feed is the next step, and it would also unlock sequencing pattern 10.
- **The zone edge is plate_x ±0.83 ft and the batter's sz_top/sz_bot,** the same edges as Step 5A. The edge band is 3 inches either side of the border.
- **This model is spatial only.** It uses where each pitch crossed the plate, not the full pitch path over time. Modeling the path, or player tracking data, is a later step.
